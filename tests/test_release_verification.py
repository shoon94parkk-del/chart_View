from datetime import datetime
import copy
import hashlib
import json
from pathlib import Path

import pytest
from scripts.validate_market_snapshot import REQUIRED, validate_market_snapshot
from scripts import verify_deployed_release as release

NOW = datetime.fromisoformat("2026-09-20T15:00:00+09:00")


def snapshot():
    return {"basis": "previous_close", "date": "2026-09-20", "results": [
        {"ticker": ticker, "price": 100, "change": 0, "asOf": "2026-09-18T20:00:00+09:00", "stale": False,
         "source": "Naver Finance KRX/Koscom" if ticker in ("^KS11", "^KQ11") else "Yahoo Chart 5m"}
        for ticker in REQUIRED
    ]}


def test_approved_korean_provider_and_closed_market():
    assert len(validate_market_snapshot(snapshot(), NOW)) == 8


@pytest.mark.parametrize("field,value", [("source", "unknown"), ("price", None), ("price", float("nan")), ("price", 0), ("asOf", ""), ("asOf", "2026-09-18T10:00:00"), ("stale", None)])
def test_invalid_market_metadata_fails(field, value):
    data = copy.deepcopy(snapshot())
    data["results"][0][field] = value
    with pytest.raises((AssertionError, ValueError)):
        validate_market_snapshot(data, NOW)


def test_wrong_revision_and_wrong_asset_fail(monkeypatch, tmp_path):
    expected = "a" * 40
    monkeypatch.setattr(release, "ROOT", tmp_path)
    contents = {}
    html = ""
    for asset in release.ASSETS:
        p = tmp_path / asset
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(asset.encode())
        url = f"/{asset}?v={hashlib.sha256(p.read_bytes()).hexdigest()[:12]}"
        contents[url] = p.read_bytes()
        html += f'<script src="{url}"></script>'
    revision = expected

    def get(base, path):
        if path.startswith("health"):
            return json.dumps({"status": "ok", "revision": revision}).encode()
        if path.startswith("?"):
            return html.encode()
        return contents[path]

    monkeypatch.setattr(release, "get", get)
    assert release.verify("https://example.test", expected, attempts=1)["revision"] == expected
    revision = "b" * 40
    with pytest.raises(ValueError, match="Expected healthy revision"):
        release.verify("https://example.test", expected, attempts=1)
    revision = expected
    contents[next(iter(contents))] = b"stale bundle"
    with pytest.raises(ValueError, match="asset mismatch"):
        release.verify("https://example.test", expected, attempts=1)
