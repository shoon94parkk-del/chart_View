"""Optional publication data must not change existing macro/Home contracts."""
import asyncio
from copy import deepcopy
import time

from fastapi.testclient import TestClient
import main


def test_macro_optional_release_data_preserves_original_cache_and_rows(monkeypatch):
    legacy = {"results": [{"symbol": str(i), "value": i} for i in range(16)],
              "summary": {"text": "unchanged", "components": {"policy": -1}},
              "generatedAt": "2026-10-15T00:00:00Z"}
    original = deepcopy(legacy)
    monkeypatch.setattr(main, "MACRO_CACHE", {"data": legacy, "timestamp": time.time()})
    extra = {"inflation": {"status": "partial", "series": [{"id": "cpi"}]},
             "releaseCalendar": {"events": [{"id": "cpi:2026-10"}]}}
    monkeypatch.setattr(main, "load_inflation_release_cache", lambda: extra, raising=False)
    response = TestClient(main.app).get("/api/macro")
    assert response.status_code == 200
    assert response.json()["inflation"] == extra["inflation"]
    assert response.json()["results"] == original["results"]
    assert response.json()["summary"] == original["summary"]
    assert legacy == original


def test_home_snapshot_does_not_ship_optional_graph_history(monkeypatch):
    legacy = {"results": [{"symbol": "DFF", "value": 4}], "summary": {"text": "unchanged"}}
    enriched = {**legacy, "inflation": {"series": [{"points": [1] * 60}]},
                "releaseCalendar": {"events": [1] * 28}}
    async def macro():
        return enriched
    async def quote(*_args):
        return {"ticker": "AAPL", "price": 100, "change": 1, "asOf": "2026-10-16T01:00:00Z"}
    monkeypatch.setattr(main, "macro_data", macro)
    monkeypatch.setattr(main, "_bulk_market_call", quote)
    monkeypatch.setattr(main, "HOME_MAJOR_TICKERS", ["AAPL"])
    monkeypatch.setattr(main, "HOME_SNAPSHOT_CACHE", {"data": None, "timestamp": 0, "refreshing": False})
    monkeypatch.setattr(main, "HOME_SNAPSHOT_LOCK", asyncio.Lock())
    result = asyncio.run(main._refresh_home_snapshot(force=True))
    assert result["macro"] == legacy
    assert "inflation" in enriched  # No mutation of the actual macro response.


def test_official_call_endpoint_is_provider_free(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("an optional static schedule reached a provider")
    monkeypatch.setattr(main.requests.sessions.Session, "request", forbidden)
    response = TestClient(main.app).get("/api/earnings-events")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cacheMode"] == "static"
    assert payload["comparison"]["status"] == "unavailable"
    assert all(row["eventType"] == "earnings_call" and row["publishedAt"] is None for row in payload["events"])
