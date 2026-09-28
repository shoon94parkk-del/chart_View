from pathlib import Path


SOURCE = Path("main.py").read_text(encoding="utf-8")


def block(start_marker: str, end_marker: str) -> str:
    start = SOURCE.index(start_marker)
    end = SOURCE.index(end_marker, start)
    return SOURCE[start:end]


def test_background_market_refresh_uses_small_isolated_executors():
    assert 'BACKGROUND_MARKET_EXECUTOR = ThreadPoolExecutor(max_workers=2' in SOURCE
    assert 'BULK_MARKET_EXECUTOR = ThreadPoolExecutor(max_workers=1' in SOURCE
    assert 'async def _background_market_call' in SOURCE
    assert 'async def _bulk_market_call' in SOURCE

    for start_marker, end_marker in [
        ('async def _refresh_home_live(', 'async def _home_live_worker('),
        ('async def _refresh_market_now(', 'def _schedule_market_now_refresh('),
    ]:
        body = block(start_marker, end_marker)
        assert '_background_market_call(fetch_quote_snapshot' in body
        assert 'asyncio.to_thread(fetch_quote_snapshot' not in body

    for start_marker, end_marker in [
        ('async def _refresh_home_snapshot(', 'def _schedule_home_snapshot_refresh('),
        ('async def _fetch_full_heatmap_quotes(', 'def _seed_full_heatmap_from_local('),
    ]:
        body = block(start_marker, end_marker)
        assert '_bulk_market_call(fetch_quote_snapshot' in body
        assert 'asyncio.to_thread(fetch_quote_snapshot' not in body


def test_stale_snapshot_refresh_is_response_first():
    market = block('def _schedule_market_now_refresh(', 'def _load_full_heatmap_us_rows(')
    home = block('def _schedule_home_snapshot_refresh(', '@app.get("/api/fwd-per")')
    assert 'await asyncio.sleep(delay)' in market
    assert 'MARKET_NOW_REFRESH_DELAY_SEC = 0.75' in SOURCE
    assert 'await asyncio.sleep(delay)' in home
    assert 'HOME_SNAPSHOT_REFRESH_DELAY_SEC = 6.0' in SOURCE
    assert 'refreshScheduled' in market
    assert 'refreshScheduled' in home


def test_activity_heartbeat_does_not_wait_for_redis():
    body = block('@app.post("/api/activity")', '@app.get("/api/home-live")')
    assert 'asyncio.create_task(_persist_daily_visitor(visitor_id))' in body
    assert 'await _persist_daily_visitor(visitor_id)' not in body


def test_quotes_reuse_fresh_shared_home_cache_before_provider():
    body = block('@app.get("/api/quotes")', '@app.get("/api/compare")')
    assert 'HOME_LIVE_CACHE.get("quotes")' in body
    assert 'marketUpdatedEpoch' in body
    assert '"sharedCacheHits": len(shared)' in body
    assert '"providerFetches": len(missing)' in body
    assert 'asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in missing' in body
