import asyncio
from pathlib import Path

import news_service_v37 as news


ROOT = Path(__file__).resolve().parents[1]


def test_news_backend_has_safe_display_policy(monkeypatch):
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_API_HUB_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    news.NEWS_CACHE.clear()

    payload = asyncio.run(news.personalized_news(tickers="005930.KS,NVDA", names="삼성전자|엔비디아"))
    assert payload["displayPolicy"] == "headline-source-time-link-only"
    assert payload["items"] == []
    assert {row["provider"] for row in payload["errors"]} == {"naver-api-hub", "finnhub"}
    assert all(row["code"] == "not_configured" for row in payload["errors"])
    assert {row["status"] for row in payload["groups"]} == {"error"}


def test_news_dedupe_prefers_higher_scored_duplicate():
    rows = [
        {"title": "Same headline", "url": "https://example.com/a", "score": 10, "publishedTs": 10},
        {"title": "Same headline", "url": "https://example.com/b", "score": 90, "publishedTs": 20},
        {"title": "Other headline", "url": "https://example.com/c", "score": 20, "publishedTs": 30},
    ]
    deduped = news._dedupe(rows)
    assert [row["url"] for row in deduped] == ["https://example.com/b", "https://example.com/c"]


def test_news_backend_accepts_full_20_symbol_watchlist(monkeypatch):
    symbols = [f"T{i:02d}" for i in range(1, 21)]

    def fake_fetch(symbol, name):
        idx = int(symbol[1:])
        if idx == 20:
            return {"items": [], "error": "provider_error:Timeout", "provider": "fake", "cache": "miss"}
        if idx == 19:
            return {"items": [], "error": None, "provider": "fake", "cache": "hit"}
        return {
            "items": [{
                "symbol": symbol, "name": name, "market": "US", "title": f"headline {symbol}",
                "source": "example", "publishedAt": "2026-09-13T00:00:00+00:00", "publishedTs": idx,
                "url": f"https://example.com/{symbol}", "provider": "fake", "score": 100 + idx,
            }],
            "error": None, "provider": "fake", "cache": "miss",
        }

    monkeypatch.setattr(news, "_cached_fetch", fake_fetch)
    payload = asyncio.run(news.personalized_news(tickers=",".join(symbols), names="|".join(symbols)))
    assert payload["requestedCount"] == 20
    assert len(payload["groups"]) == 20
    assert payload["groups"][18]["status"] == "no_news"
    assert payload["groups"][19]["status"] == "error"
    assert payload["providerConcurrency"] == 4


def test_v40_frontend_assets_and_home_order_are_wired():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    frontend = (ROOT / "static/js/personalized_news_v40.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/release_ui_v40.css").read_text(encoding="utf-8")
    backend = (ROOT / "news_service_v37.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "/static/js/personalized_news_v40.js?v=20260913stage12" in boot
    assert "/static/js/personalized_news_v38.js" not in boot
    assert "/static/css/personalized_news_v38.css?v=20260913v38" in boot  # legacy visual layer only
    assert "market-watchlist-news-body-status" in boot
    assert "home.dataset.newsVersion = 'v40'" in boot
    assert "MAX_SYMBOLS = 20" in frontend
    assert "AbortController" in frontend
    assert "hydrateMarket(section, items, seq).catch" in frontend
    assert "이벤트 참고 설명" in frontend
    assert "관심종목별 조회 상태" in frontend
    assert "5거래일 가격 흐름" in frontend
    assert "Impact Score" not in frontend
    assert "min-height: 44px" in css
    assert "app.include_router(news_router_v37)" in main
    assert '"image"' not in backend
