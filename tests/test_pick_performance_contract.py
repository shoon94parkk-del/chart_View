from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_home_watchlist_keeps_one_month_return_and_four_item_summary():
    compact = read("static/js/home_watchlist_compact_v46.js")
    html = read("templates/index.html")

    assert "MY STOCKS · 1달 수익률" in compact
    assert "const HOME_VISIBLE = 4" in compact
    assert "slice(0, HOME_VISIBLE)" in compact
    assert ">더보기 →</button>" in compact
    assert "recommendation_watchlist_v55.js" not in html


def test_chartview_pick_uses_recommendation_close_to_current_price():
    html = read("templates/index.html")
    path = Path("static/js/pick_performance_v56.js")

    assert "/static/js/pick_performance_v56.js?v=20260917v56" in html
    assert path.exists(), "PICK performance layer must exist"

    script = path.read_text(encoding="utf-8")
    assert "/static/data/ai_recommendations.json" in script
    assert "recommendedPrice" in script
    assert "currentPrice" in script
    assert "/api/compare?tickers=" in script
    assert "추천 종가" in script
    assert "→ 현재" in script
    assert ".ai-daily-rank" in script and ".remove()" in script
