from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_recommendation_watchlist_module_exists_and_is_loaded():
    module = ROOT / 'static/js/recommendation_watchlist_v55.js'
    assert module.exists()
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert '/static/js/recommendation_watchlist_v55.js?v=20260917v55' in html


def test_watchlist_uses_recommendation_close_not_one_month_return():
    js = (ROOT / 'static/js/recommendation_watchlist_v55.js').read_text(encoding='utf-8')
    assert 'ai_recommendations.json' in js
    assert 'recommendedPrice' in js
    assert 'recommendedDate' in js
    assert 'currentValue / base - 1' in js
    assert '추천 기록 없음' in js
    assert '1달 수익률' not in js


def test_home_watchlist_is_four_items_and_pick_rank_is_hidden():
    js = (ROOT / 'static/js/recommendation_watchlist_v55.js').read_text(encoding='utf-8')
    assert 'HOME_VISIBLE = 4' in js
    assert 'index >= HOME_VISIBLE' in js
    assert '.ai-daily-rank' in js
