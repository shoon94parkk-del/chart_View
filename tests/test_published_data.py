"""Regression tests: PICK prices follow GitHub publication, not Render deploys."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import published_data as module


def _data(updated, price):
    return {"updated": updated, "recommendations": [{"symbol": "069500.KS", "currentPrice": price}]}


class _Response:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return self.content


def test_reads_new_selection_price_without_deployment():
    old = _data("2026-10-15T16:00:00+09:00", 87025)
    new = _data("2026-10-19T16:41:35+09:00", 89930)
    with tempfile.TemporaryDirectory() as temp:
        Path(temp, "ai_recommendations.json").write_text(json.dumps(old), encoding="utf-8")
        with patch.object(module, "_DATA_DIR", Path(temp)), patch.object(module, "_CACHE", {}):
            with patch.object(module, "urlopen", return_value=_Response(json.dumps(new).encode())):
                result, source = module.get_published_data("ai_recommendations.json")
            assert source == "github-main"
            assert result["recommendations"][0]["currentPrice"] == 89930


def test_stale_cdn_copy_cannot_rollback_current_price():
    current = _data("2026-10-19T16:41:35+09:00", 89930)
    older = _data("2026-10-15T16:00:00+09:00", 87025)
    with tempfile.TemporaryDirectory() as temp:
        Path(temp, "ai_recommendations.json").write_text(json.dumps(current), encoding="utf-8")
        with patch.object(module, "_DATA_DIR", Path(temp)), patch.object(module, "_CACHE", {}):
            with patch.object(module, "urlopen", return_value=_Response(json.dumps(older).encode())):
                result, source = module.get_published_data("ai_recommendations.json")
            assert source == "deployment-fallback"
            assert result["recommendations"][0]["currentPrice"] == 89930


def test_github_failure_uses_dated_local_data_and_avoids_invented_freshness():
    previous = _data("2026-10-15T16:00:00+09:00", 87025)
    with tempfile.TemporaryDirectory() as temp:
        Path(temp, "ai_recommendations.json").write_text(json.dumps(previous), encoding="utf-8")
        with patch.object(module, "_DATA_DIR", Path(temp)), patch.object(module, "_CACHE", {}):
            with patch.object(module, "urlopen", side_effect=URLError("offline")):
                result, source = module.get_published_data("ai_recommendations.json")
            assert source == "deployment-fallback"
            assert result["updated"].startswith("2026-10-15")


def test_does_not_allow_arbitrary_repository_paths():
    try:
        module.get_published_data("../../.env")
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected unrestricted file path")
