from pathlib import Path


def test_v36_visual_asset_is_preserved_but_detail_js_is_replaced():
    boot = Path('static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    assert '/static/css/personalization_v36.css?v=20260912v36' in boot
    assert '/static/js/personalization_v36.js' not in boot
    assert '/static/js/single_detail_v40.js?v=20260913stage12' in boot
    assert "home.dataset.homeOrder = 'market-watchlist-news-body-status'" in boot


def test_single_stock_detail_does_not_auto_mutate_compare_list():
    js = Path('static/js/single_detail_v40.js').read_text(encoding='utf-8')
    start = js.index('async function openDetail')
    end = js.index('function hideDetail')
    open_detail = js[start:end]
    assert 'window.addGlobalTicker' not in open_detail
    assert '비교에 추가' in js
    assert '비교 중' in js
    assert '비교목록 관리' in js


def test_compare_and_storage_state_are_owned_by_shared_state_module():
    js = Path('static/js/app_state_v40.js').read_text(encoding='utf-8')
    assert 'chartview-watchlist-v1' in js
    assert 'chartview-selected-tickers-v1' in js
    assert 'getCompare' in js and 'setCompare' in js
    assert "window.addEventListener('storage'" not in js  # no page reload owner; explicit modules react to scoped changes


def test_detail_exposes_period_and_price_basis():
    js = Path('static/js/single_detail_v40.js').read_text(encoding='utf-8')
    for text in ('관측', '가격 기준', '거래 기준', '1달 수익률 차트'):
        assert text in js
