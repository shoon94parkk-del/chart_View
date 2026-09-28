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


def test_quotes_fresh_mode_bypasses_shared_home_cache():
    source = Path("main.py").read_text(encoding="utf-8")
    start = source.index('@app.get("/api/quotes")')
    end = source.index('@app.get("/api/compare")', start)
    block = source[start:end]
    assert "async def quote_snapshots(tickers: str, fresh: bool = False)" in block
    assert "if not fresh and ticker in HOME_MAJOR_TICKERS" in block
    assert '"freshRequested": bool(fresh)' in block
