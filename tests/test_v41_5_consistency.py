from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_five_day_chart_uses_daily_period_basis():
    market = (ROOT / 'market_service.py').read_text(encoding='utf-8')
    assert '"5d": "1d"' in market


def test_home_news_sparkline_uses_full_five_day_series():
    js = (ROOT / 'static/js/personalized_news_v40.js').read_text(encoding='utf-8')
    assert '.slice(-20)' not in js
    assert 'const source = (Array.isArray(values) ? values : []).map(Number).filter(Number.isFinite);' in js
    assert 'pickDiverse(payload?.items, TOP_COUNT)' in js


def test_market_has_one_canonical_toggle_and_no_global_polish_observer():
    polish = (ROOT / 'static/js/home_polish_v41_4.js').read_text(encoding='utf-8')
    release = (ROOT / 'static/js/release_ui_v40.js').read_text(encoding='utf-8')
    assert 'data-v415-market-toggle' in polish
    assert "panel.querySelector('[data-home23-market-toggle]')" in release
    assert 'observer.observe(document.documentElement' not in polish


def test_v415_client_assets_are_cache_busted():
    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    for asset in (
        '/static/js/personalized_news_v40.js?v=20260913v415',
        '/static/js/news_readability_v41_2.js?v=20260913v415',
        '/static/js/release_ui_v40.js?v=20260913v415',
        '/static/js/home_polish_v41_4.js?v=20260913v415',
    ):
        assert asset in boot
    assert '/static/js/home_watchlist_boot_v32c.js?v=20260913v415' in html
