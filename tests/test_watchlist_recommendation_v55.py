from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_recommendation_watchlist_module_exists_and_is_loaded():
    module = ROOT / 'static/js/recommendation_watchlist_v55.js'
    assert module.exists()
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert '/static/js/recommendation_watchlist_v55.js?v=20260917v56' in html


def test_watchlist_keeps_one_month_return_contract():
    watchlist = (ROOT / 'static/js/watchlist_v30.js').read_text(encoding='utf-8')
    overlay = (ROOT / 'static/js/recommendation_watchlist_v55.js').read_text(encoding='utf-8')

    assert 'MY STOCKS · 1달 수익률' in watchlist
    assert '현재가와 1달 수익률' in watchlist
    assert '수익률 높은순' in watchlist
    assert '수익률 낮은순' in watchlist

    for token in ('#home-watchlist-v30', '#watchlist-tab', 'data-home-watch-return', 'data-watch-return'):
        assert token not in overlay


def test_chartview_pick_uses_recommendation_close_to_current_price():
    js = (ROOT / 'static/js/recommendation_watchlist_v55.js').read_text(encoding='utf-8')

    assert 'ai_recommendations.json' in js
    assert 'recommendedPrice' in js
    assert 'recommendedDate' in js
    assert 'currentPrice' in js
    assert 'returnPct' in js
    assert 'current / base - 1' in js
    assert '#ai-daily-section' in js
    assert '.ai-daily-price' in js
    assert '추천' in js and '현재' in js
    assert '.ai-daily-rank' in js
