from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_home_watchlist_keeps_one_month_return_and_four_item_summary():
    compact = read("static/js/home_watchlist_compact_v46.js")
    layer = read("static/js/recommendation_watchlist_v55.js")

    assert "MY STOCKS · 1달 수익률" in compact
    assert "const HOME_VISIBLE = 4" in layer
    assert "더보기 →" in layer
    assert "MY STOCKS · 추천 후 수익률" not in layer
    assert "syncWatchlistHeader" not in layer
    assert "syncWatchlistCards" not in layer


def test_chartview_pick_uses_recommendation_close_to_current_price():
    script = read("static/js/recommendation_watchlist_v55.js")

    assert "/static/data/ai_recommendations.json" in script
    assert "recommendedPrice" in script
    assert "currentPrice" in script
    assert "/api/compare?tickers=" in script
    assert "추천 종가" in script
    assert "→ 현재" in script
    assert ".ai-daily-rank" in script and ".remove()" in script
