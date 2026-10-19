from pathlib import Path


def _block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_home_bootstrap_reads_fresh_published_data_without_shared_stale_cache():
    source = Path("main.py").read_text(encoding="utf-8")
    block = _block(source, '@app.get("/api/home-bootstrap")', '@app.get("/api/popular")')
    assert 'get_published_data, "ai_daily_rankings.json"' in block
    assert 'get_published_data, "ai_recommendations.json"' in block
    assert 'no-store, max-age=0, must-revalidate' in block


def test_market_now_normal_reads_are_cacheable_but_fresh_reads_are_not():
    source = Path("main.py").read_text(encoding="utf-8")
    block = _block(source, '@app.get("/api/market-now")', 'def _load_full_heatmap_us_rows')
    assert 'if fresh' in block
    assert '"no-store"' in block
    assert 'public, max-age=5, s-maxage=5, stale-while-revalidate=20' in block
    assert 'JSONResponse(content=payload, headers=headers)' in block
