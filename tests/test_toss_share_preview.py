from pathlib import Path
import ast
import html
import json
import re
import unittest
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")


def preview_functions():
    tree = ast.parse(SOURCE)
    names = {"TOSS_SHARE_TITLES", "TOSS_SHARE_ORIGIN", "TOSS_SHARE_URL"}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names for target in node.targets):
            selected.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in {"_toss_share_name", "toss_share_page"}:
            node.decorator_list = []
            node.returns = None
            for arg in node.args.args:
                arg.annotation = None
            selected.append(node)
    class Response:
        def __init__(self, body, headers=None):
            self.body = body.encode("utf-8")
            self.headers = headers or {}
    class HttpError(Exception):
        def __init__(self, status_code, detail=""):
            self.status_code = status_code
            self.detail = detail
    scope = {
        "re": re, "json": json, "html_escape": html.escape, "url_quote": quote,
        "Query": lambda default="", **kwargs: default,
        "HTTPException": HttpError, "HTMLResponse": Response,
        "STOCK_DATABASE": [],
        "load_krx_stock_list": lambda: [{"code": "066570", "name": "LG전자", "suffix": ".KS"}],
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), "main.py", "exec"), scope)
    return scope["toss_share_page"], HttpError


class TossSharePreviewTest(unittest.TestCase):
    def test_detail_metadata_is_crawler_readable_and_opens_exact_stock(self):
        endpoint, _ = preview_functions()
        html = endpoint("detail", "066570.KS").body.decode("utf-8")
        self.assertIn("LG전자 (066570.KS) | 차트뷰", html)
        self.assertIn('property="og:image"', html)
        self.assertIn('https://chart-view-toss.onrender.com/marketing/chartview-toss-instagram-20260930.png', html)
        self.assertIn('property="og:image:width" content="1122"', html)
        self.assertIn('property="og:image:height" content="1402"', html)
        self.assertIn('name="twitter:card" content="summary_large_image"', html)
        self.assertIn("#detail/066570.KS", html)

    def test_chart_metadata_and_invalid_symbol(self):
        endpoint, HttpError = preview_functions()
        html = endpoint("chart", "").body.decode("utf-8")
        self.assertIn("수익률 비교 | 차트뷰", html)
        self.assertIn("#chart", html)
        with self.assertRaises(HttpError):
            endpoint("detail", "bad<script>")
        with self.assertRaises(HttpError):
            endpoint("unknown", "")


if __name__ == "__main__":
    unittest.main()
