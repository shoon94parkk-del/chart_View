"""Regression tests: PICK prices follow GitHub publication, not Render deploys."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
import pytest

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


def _memory_data(stamp):
    from memory_spot_service import _merge_group_results, _merge_history
    payload = _merge_group_results([], {})
    dram = payload["groups"][0]
    dram.update(sourceDate=stamp[:10], updatedAt=stamp[:10] + "T18:10:00+08:00", stale=False)
    payload = _merge_group_results([payload], {})
    return {**payload, "schemaVersion": 2, "generatedAt": stamp, "collectedAt": stamp,
            "history": _merge_history([], payload)}


@pytest.mark.parametrize("remote_kind", ["older", "invalid", "offline"])
def test_memory_publication_keeps_newest_history_after_cache_expiry(tmp_path, monkeypatch, remote_kind):
    filename = "memory_prices.json"
    local = _memory_data("2026-11-08T10:35:00Z")
    current = _memory_data("2026-11-10T10:35:00Z")
    (tmp_path / filename).write_text(json.dumps(local), encoding="utf-8")
    monkeypatch.setattr(module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(module, "_CACHE", {})
    monkeypatch.setattr(module, "urlopen", lambda *_args, **_kwargs: _Response(json.dumps(current).encode()))
    first, source = module.get_published_data(filename)
    assert source == "github-main"
    assert first["history"][-1]["date"] == "2026-11-10"
    module._CACHE[filename] = (0, first, source)
    if remote_kind == "offline":
        def offline(*_args, **_kwargs):
            raise URLError("offline")
        monkeypatch.setattr(module, "urlopen", offline)
    else:
        remote = local if remote_kind == "older" else {**current, "history": [{"date": "2026-11-10", "values": {"ddr5-16gb": True}}]}
        monkeypatch.setattr(module, "urlopen", lambda *_args, **_kwargs: _Response(json.dumps(remote).encode()))
    result, source = module.get_published_data(filename)
    assert result == first
    assert source == "cached-published-fallback"
