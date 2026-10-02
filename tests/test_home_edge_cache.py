from pathlib import Path


def _block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_home_bootstrap_is_shared_cacheable():
    source = Path("main.py").read_text(encoding="utf-8")
    block = _block(source, '@app.get("/api/home-bootstrap")', '@app.get("/api/popular")')
    assert 'public, max-age=60, s-maxage=300, stale-while-revalidate=3600' in block
    assert 'no-cache, max-age=0, must-revalidate' not in block


def test_market_now_normal_reads_are_cacheable_but_fresh_reads_are_not():
    source = Path("main.py").read_text(encoding="utf-8")
    block = _block(source, '@app.get("/api/market-now")', 'def _load_full_heatmap_us_rows')
    assert 'if fresh' in block
    assert '"no-store"' in block
    assert 'public, max-age=5, s-maxage=5, stale-while-revalidate=20' in block
    assert 'JSONResponse(content=payload, headers=headers)' in block
