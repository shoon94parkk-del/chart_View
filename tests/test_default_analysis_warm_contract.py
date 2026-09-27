from pathlib import Path


MAIN = Path("main.py").read_text(encoding="utf-8")
MARKET = Path("market_service.py").read_text(encoding="utf-8")


def test_default_toss_analysis_is_prewarmed_on_background_pool():
    assert 'DEFAULT_APP_ANALYSIS_TICKERS = ["005930.KS", "NVDA", "AAPL"]' in MAIN
    assert 'async def _warm_default_app_analysis()' in MAIN
    assert '_background_market_call(fetch_compare_stock, ticker, "1mo", None, None)' in MAIN
    assert '_background_market_call(fetch_valuation_snapshot, ticker)' in MAIN
    assert 'asyncio.create_task(_warm_default_app_analysis())' in MAIN


def test_compare_cache_lasts_five_minutes():
    start = MARKET.index("def fetch_compare_stock")
    block = MARKET[start:start + 1800]
    assert "now - cached[0] < 300" in block
    assert "now - cached[0] < 60" not in block
