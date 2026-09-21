import ast
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient


def test_real_screener_payload_compresses_without_changing_values():
    app = FastAPI()
    source = ast.parse(Path('main.py').read_text(encoding='utf-8'))
    statement = next(node for node in source.body if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call) and node.value.args
        and isinstance(node.value.args[0], ast.Name) and node.value.args[0].id == 'GZipMiddleware')
    exec(compile(ast.Module(body=[statement], type_ignores=[]), 'gzip-config', 'exec'),
         {'app': app, 'GZipMiddleware': GZipMiddleware})
    data = json.loads(Path('static/data/screener.json').read_text(encoding='utf-8'))
    @app.get('/data')
    def payload():
        return data
    with TestClient(app) as http:
        compressed = http.get('/data', headers={'Accept-Encoding': 'gzip'})
        plain = http.get('/data', headers={'Accept-Encoding': 'identity'})
        assert compressed.json() == plain.json() == data
        assert compressed.headers['content-encoding'] == 'gzip'
        assert int(compressed.headers['content-length']) < len(plain.content) * .3
        print(f'JSON wire bytes: {len(plain.content)} -> {compressed.headers["content-length"]}')
