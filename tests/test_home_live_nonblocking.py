from pathlib import Path


def test_home_live_request_path_never_waits_for_provider_refresh():
    source = Path("main.py").read_text(encoding="utf-8")
    start = source.index('@app.get("/api/home-live")')
    end = source.index('@app.get("/admin/usage")', start)
    block = source[start:end]

    assert "await _refresh_home_live" not in block
    assert "fetch_quote_snapshot" not in block
    assert "HOME_LIVE_WAKE_EVENT.set()" in block
    assert 'Cache-Control": "no-store"' in block
