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
    widget = read("static/js/ai_daily_widget.js")

    assert "/static/data/ai_recommendations.json" in widget
    assert "recommendedPrice" in widget
    assert "currentPrice" in widget
    assert "/api/compare?tickers=" in widget
    assert "추천 종가" in widget
    assert "→ 현재" in widget
    assert "ai-daily-rank\">" not in widget
