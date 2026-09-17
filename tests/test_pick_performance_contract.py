from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_home_watchlist_keeps_one_month_return_and_four_item_summary():
    compact = read("static/js/home_watchlist_compact_v46.js")
    html = read("templates/index.html")
    path = Path("static/js/pick_performance_v56.js")

    assert "MY STOCKS · 1달 수익률" in compact
    assert path.exists(), "PICK performance layer must also keep Home summary compact"
    script = path.read_text(encoding="utf-8")
    assert "const HOME_VISIBLE = 4" in script
    assert "MY STOCKS · 1달 수익률" in script
    assert "추천 후 수익률" not in script
    assert "syncWatchlistCards" not in script
    assert "recommendation_watchlist_v55.js" not in html
    assert "/static/js/pick_performance_v56.js?v=20260917v56" in html


def test_chartview_pick_uses_recommendation_close_to_current_price():
    script = read("static/js/pick_performance_v56.js")

    assert "/static/data/ai_recommendations.json" in script
    assert "recommendedPrice" in script
    assert "currentPrice" in script
    assert "/api/compare?" in script
    assert "추천 " in script and " 종가 " in script
    assert "→ 현재 " in script
    assert ".ai-daily-rank" in script and ".remove()" in script
