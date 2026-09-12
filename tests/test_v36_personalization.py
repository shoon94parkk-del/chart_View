from pathlib import Path


def test_v36_personalization_assets_are_loaded():
    boot = Path('static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    assert '/static/js/personalization_v36.js?v=20260912v36' in boot
    assert '/static/css/personalization_v36.css?v=20260912v36' in boot
    assert "home.dataset.homeOrder = 'market-watchlist-body-status'" in boot


def test_single_stock_detail_does_not_auto_mutate_compare_list():
    js = Path('static/js/personalization_v36.js').read_text(encoding='utf-8')
    start = js.index('async function openDetail')
    end = js.index('function interceptDetailNavigation')
    open_detail = js[start:end]
    assert 'window.addGlobalTicker' not in open_detail
    assert 'data-v36-compare' in js
    assert '비교에 추가' in js
    assert '비교목록과 별도' in js


def test_cross_tab_storage_changes_are_handled():
    js = Path('static/js/personalization_v36.js').read_text(encoding='utf-8')
    assert "window.addEventListener('storage', handleStorage)" in js
    assert 'chartview-watchlist-v1' in js
    assert 'chartview-selected-tickers-v1' in js


def test_detail_exposes_period_and_price_basis():
    js = Path('static/js/personalization_v36.js').read_text(encoding='utf-8')
    for text in ('실제 비교 구간', '관측 수', '가격 기준', '시장 휴장일·신규 상장'):
        assert text in js
