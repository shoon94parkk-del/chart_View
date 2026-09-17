from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_recommendation_watchlist_layer_is_not_loaded():
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert '/static/js/recommendation_watchlist_v55.js' not in html
    assert '/static/js/pick_performance_v56.js?v=20260917v56' in html


def test_watchlist_keeps_one_month_return_while_home_is_compact():
    compact = (ROOT / 'static/js/home_watchlist_compact_v46.js').read_text(encoding='utf-8')
    pick = (ROOT / 'static/js/pick_performance_v56.js').read_text(encoding='utf-8')
    assert 'MY STOCKS · 1달 수익률' in compact
    assert 'MY STOCKS · 1달 수익률' in pick
    assert 'HOME_VISIBLE = 4' in pick
    assert 'index >= HOME_VISIBLE' in pick
    assert '추천 후 수익률' not in pick
    assert 'syncWatchlistCards' not in pick


def test_pick_uses_recommendation_close_and_hides_rank():
    js = (ROOT / 'static/js/pick_performance_v56.js').read_text(encoding='utf-8')
    assert 'ai_recommendations.json' in js
    assert 'recommendedPrice' in js
    assert 'recommendedDate' in js
    assert '(current / base - 1) * 100' in js
    assert '/api/compare?' in js
    assert '추천 ${esc(compactDate(rec.recommendedDate))} 종가' in js
    assert '→ 현재' in js
    assert '.ai-daily-rank' in js
