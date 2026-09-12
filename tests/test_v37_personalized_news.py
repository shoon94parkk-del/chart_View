import asyncio
from pathlib import Path

import news_service_v37 as news


ROOT = Path(__file__).resolve().parents[1]


def test_v37_backend_has_safe_display_policy(monkeypatch):
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    news.NEWS_CACHE.clear()

    payload = asyncio.run(
        news.personalized_news(
            tickers="005930.KS,NVDA",
            names="삼성전자|엔비디아",
        )
    )

    assert payload["displayPolicy"] == "headline-source-time-link-only"
    assert payload["items"] == []
    assert {row["provider"] for row in payload["errors"]} == {"naver-api-hub", "finnhub"}
    assert all(row["code"] == "not_configured" for row in payload["errors"])


def test_v37_dedupe_prefers_higher_scored_duplicate():
    rows = [
        {"title": "Same headline", "url": "https://example.com/a", "score": 10, "publishedTs": 10},
        {"title": "Same headline", "url": "https://example.com/b", "score": 90, "publishedTs": 20},
        {"title": "Other headline", "url": "https://example.com/c", "score": 20, "publishedTs": 30},
    ]
    deduped = news._dedupe(rows)
    assert [row["url"] for row in deduped] == ["https://example.com/b", "https://example.com/c"]


def test_v37_frontend_assets_and_home_order_are_wired():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/personalized_news_v37.js").read_text(encoding="utf-8")
    backend = (ROOT / "news_service_v37.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "/static/js/personalized_news_v37.js?v=20260912v37" in boot
    assert "/static/css/personalized_news_v37.css?v=20260912v37" in boot
    assert "market-watchlist-news-body-status" in boot
    assert "home-personal-news-v37" in frontend
    assert "기사 제목·출처·게시시각만 표시" in frontend
    assert "app.include_router(news_router_v37)" in main
    assert "description" not in backend.split("items.append({", 1)[1].split("})", 1)[0]
    assert '"image"' not in backend
