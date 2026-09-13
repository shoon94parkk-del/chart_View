from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_five_day_chart_uses_daily_period_basis():
    market = (ROOT / 'market_service.py').read_text(encoding='utf-8')
    assert '"5d": "1d"' in market


def test_home_news_sparkline_uses_full_five_day_series():
    js = (ROOT / 'static/js/personalized_news_v40.js').read_text(encoding='utf-8')
    assert '.slice(-20)' not in js
    assert 'pickDiverse(payload?.items, TOP_COUNT)' in js


def test_market_has_one_canonical_toggle_and_ready_event():
    polish = (ROOT / 'static/js/home_polish_v41_4.js').read_text(encoding='utf-8')
    market = (ROOT / 'static/js/home_market_v9.js').read_text(encoding='utf-8')
    assert 'data-v415-market-toggle' in polish
    assert 'chartview:market-panel-ready' in polish and 'chartview:market-panel-ready' in market
    assert '<i>⌄</i>' not in polish


def test_current_client_assets_are_cache_busted():
    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    for name in ('personalized_news_v40.js','news_readability_v41_2.js','my_hub_v41.js','resilience_v41_3.js','single_detail_v40.js','detail_visibility_v40_1.js','home_polish_v41_4.js'):
        assert f'/static/js/{name}?v=' in boot
    assert '/static/js/home_watchlist_boot_v32c.js?v=' in html
