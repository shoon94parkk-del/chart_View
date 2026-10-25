"""Home must count the same publication without sending the full universe."""
import importlib
import importlib.util
import json
import threading
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def service():
    assert importlib.util.find_spec("home_screener_service"), "Home summary service is available"
    return importlib.import_module("home_screener_service")


def client():
    app = FastAPI()
    app.include_router(service().router)
    return TestClient(app)


def test_summary_counts_the_full_universe_with_javascript_finite_number_semantics():
    # The legacy JS predicate accepts Number coercion, including numeric strings
    # and singleton arrays, but excludes blank/null/nonfinite observations.
    values = [None, "", " ", 1.99, 2, " 2.4 ", 3, "0x2", "0b10", "0o2",
              "2e0", [2], [["2"]], [], {}, True, "2_000", "Infinity", "NaN",
              "-0x2", "\u00852", "\ufeff2\ufeff", "2\u200b", "٢", [None, 2]]
    payload = {"tradeDate": "2026-10-02", "updated": "2026-10-03T01:00:00Z",
               "source": "published-close", "stocks": [{"volumeRatio": value} for value in values]}
    original = json.dumps(payload)
    with patch("published_data.get_published_data", return_value=(payload, "github-main")):
        response = client().get("/api/home-screener-summary")
    assert response.status_code == 200
    assert response.json() == {"schemaVersion": 1, "tradeDate": "2026-10-02",
                               "updated": "2026-10-03T01:00:00Z", "source": "published-close",
                               "counts": {"volumeSurge": 10}}
    assert json.dumps(payload) == original


def test_summary_preserves_source_state_and_real_dates_without_returning_stock_rows():
    payload = {"updated": "2026-10-03T01:00:00Z", "pending": True, "refreshing": True,
               "available": False, "error": "saved source unavailable", "status": "pending",
               "stocks": [{"volumeRatio": 2, "symbol": f"{i:06d}.KS", "score": 99} for i in range(3000)]}
    with patch("published_data.get_published_data", return_value=(payload, "cached-published-fallback")):
        response = client().get("/api/home-screener-summary")
    body = response.json()
    assert body["counts"] == {"volumeSurge": 3000}
    assert "tradeDate" not in body
    for field in ("updated", "pending", "refreshing", "available", "error", "status"):
        assert body[field] == payload[field]
    assert "stocks" not in body and "score" not in response.text
    assert len(response.content) < 1024
    assert response.headers["x-chartview-data-source"] == "cached-published-fallback"
    assert response.headers["x-chartview-data-asof"] == payload["updated"]
    assert "no-store" in response.headers["cache-control"]


def test_summary_uses_the_existing_reader_off_the_request_event_loop_without_a_second_cache():
    event_threads = []
    read_threads = []
    app = FastAPI()
    app.include_router(service().router)

    @app.middleware("http")
    async def record_thread(request, call_next):
        event_threads.append(threading.get_ident())
        return await call_next(request)

    def read(filename):
        assert filename == "screener.json"
        read_threads.append(threading.get_ident())
        return {"tradeDate": "2026-10-02", "stocks": [{"volumeRatio": 2}] * len(read_threads)}, "deployment-fallback"

    with patch("published_data.get_published_data", side_effect=read):
        with TestClient(app) as http:
            first = http.get("/api/home-screener-summary")
            second = http.get("/api/home-screener-summary")
    assert first.json()["counts"] == {"volumeSurge": 1}
    assert second.json()["counts"] == {"volumeSurge": 2}
    assert len(read_threads) == 2
    assert all(worker != event for worker, event in zip(read_threads, event_threads))


def test_summary_reader_failures_and_invalid_universes_are_not_successful_zero_counts():
    for payload in ({}, {"stocks": None}, {"stocks": {}}, {"stocks": [None]}):
        with patch("published_data.get_published_data", return_value=(payload, "deployment-fallback")):
            assert client().get("/api/home-screener-summary").status_code == 503
    with patch("published_data.get_published_data", side_effect=RuntimeError("private reader failure")):
        response = client().get("/api/home-screener-summary")
    assert response.status_code == 503
    assert "private reader failure" not in response.text


def test_an_actual_empty_universe_is_a_dated_zero_count():
    with patch("published_data.get_published_data", return_value=({"tradeDate": "2026-10-02", "stocks": []}, "github-main")):
        response = client().get("/api/home-screener-summary")
    assert response.status_code == 200
    assert response.json()["counts"] == {"volumeSurge": 0}
