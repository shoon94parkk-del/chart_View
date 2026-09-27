from pathlib import Path


MAIN = Path("main.py").read_text(encoding="utf-8")
MARKET = Path("market_service.py").read_text(encoding="utf-8")


def test_default_toss_analysis_is_prewarmed_on_background_pool():
    assert 'DEFAULT_APP_ANALYSIS_TICKERS = ["005930.KS", "NVDA", "AAPL"]' in MAIN
    assert 'async def _warm_default_app_analysis()' in MAIN
    assert '_background_market_call(fetch_compare_stock, ticker, "1mo", None, None)' in MAIN
    assert '_background_market_call(fetch_valuation_snapshot, ticker)' in MAIN
    assert 'asyncio.create_task(_warm_default_app_analysis())' in MAIN


def test_compare_cache_uses_stale_while_revalidate():
    assert "COMPARE_CACHE_FRESH_TTL_SECONDS = 300.0" in MARKET
    assert 'ThreadPoolExecutor(max_workers=2, thread_name_prefix="chartview-compare-refresh")' in MARKET
    assert "def _schedule_compare_refresh(" in MARKET
    start = MARKET.index("def get_compare_cache")
    block = MARKET[start:start + 2600]
    assert "age >= COMPARE_CACHE_FRESH_TTL_SECONDS" in block
    assert "_schedule_compare_refresh(" in block
    assert "return True, cached_value" in block
    assert "COMPARE_CACHE_FAILURE_TTL_SECONDS" in block
    fetch_start = MARKET.index("def fetch_compare_stock")
    fetch_block = MARKET[fetch_start:fetch_start + 1000]
    assert "get_compare_cache(symbol, period, start, end)" in fetch_block


def test_startup_prioritizes_blocking_user_caches_before_bulk_refreshes():
    start = MAIN.index('async def startup_event():')
    block = MAIN[start:start + 3600]
    market_pos = block.index('await asyncio.wait_for(_refresh_market_now(force=True), timeout=12.0)')
    analysis_pos = block.index('await asyncio.wait_for(_warm_default_app_analysis(), timeout=12.0)')
    home_live_pos = block.index('asyncio.create_task(_refresh_home_live(_all_home_markets()))')
    full_heatmap_pos = block.index('asyncio.create_task(_refresh_full_heatmap(force=True))')
    assert market_pos < analysis_pos < home_live_pos < full_heatmap_pos
    assert '[STARTUP_WARM]' in block
    assert 'asyncio.create_task(_refresh_market_now(force=True))' not in block
    assert 'asyncio.create_task(_warm_default_app_analysis())' not in block
