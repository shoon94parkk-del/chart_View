from datetime import datetime, timezone
import asyncio
import inspect
import time

import main


def test_home_market_windows_are_split_by_exchange_hours():
    kr_open = main._open_home_markets(datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc))
    assert "KR" in kr_open and "US" not in kr_open
    assert len(kr_open["KR"]) == 8

    us_open = main._open_home_markets(datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc))
    assert "US" in us_open and "KR" not in us_open
    assert len(us_open["US"]) == 10


def test_home_live_endpoint_is_memory_only():
    source = inspect.getsource(main.home_live_snapshot)
    assert "fetch_quote_snapshot" not in source
    assert "_home_live_results()" in source
    assert "Render shared memory" in source


def test_background_worker_is_activity_gated():
    source = inspect.getsource(main._home_live_worker)
    assert "is_active_home" in source
    assert "HOME_LIVE_ACTIVE_REFRESH_SEC" in source
    assert "HOME_LIVE_FIRST_VISITOR_GRACE_SEC" in source
    assert "if not was_active_home" in source
    assert "_refresh_home_live(due)" in source


def test_anonymous_visitor_count_does_not_store_raw_id():
    main.VISITOR_LAST_SEEN.clear()
    main.VISITOR_DAILY.clear()
    raw = "visitor-test-12345678"
    active, active_home = main._record_visitor(raw, "home")
    assert active == 1
    assert active_home == 1
    day = main._today_kst()
    keys = list(main.VISITOR_DAILY[day])
    assert len(keys) == 1
    assert raw not in keys[0]


def test_admin_usage_requires_env_token(monkeypatch):
    monkeypatch.setenv("CHARTVIEW_ADMIN_TOKEN", "secret-test")
    source = inspect.getsource(main._admin_token_ok)
    assert "compare_digest" in source
    assert "X-ChartView-Admin" in source


def test_shared_quote_cache_freshness_is_per_ticker(monkeypatch):
    old_cache = {
        "quotes": dict(main.HOME_LIVE_CACHE.get("quotes") or {}),
        "marketUpdatedEpoch": dict(main.HOME_LIVE_CACHE.get("marketUpdatedEpoch") or {}),
        "quoteUpdatedEpoch": dict(main.HOME_LIVE_CACHE.get("quoteUpdatedEpoch") or {}),
    }
    try:
        main.HOME_LIVE_CACHE["quotes"] = {
            "005930.KS": {
                "ticker": "005930.KS",
                "price": 274000,
                "change": -4.03,
                "asOf": "2026-09-28T13:37:00+09:00",
            }
        }
        main.HOME_LIVE_CACHE["marketUpdatedEpoch"] = {"KR": time.time(), "US": 0.0}
        main.HOME_LIVE_CACHE["quoteUpdatedEpoch"] = {}
        monkeypatch.setattr(main, "_open_home_markets", lambda *_args, **_kwargs: {"KR": ["005930.KS"]})
        monkeypatch.setattr(main, "fetch_quote_snapshot", lambda ticker: {
            "ticker": ticker,
            "price": 280000,
            "change": -2.0,
            "asOf": "2026-09-28T15:30:00+09:00",
        })

        payload = asyncio.run(main.quote_snapshots("005930.KS"))
        assert payload["sharedCacheHits"] == 0
        assert payload["providerFetches"] == 1
        assert payload["results"][0]["price"] == 280000
        assert main.HOME_LIVE_CACHE["quoteUpdatedEpoch"]["005930.KS"] > 0
    finally:
        main.HOME_LIVE_CACHE["quotes"] = old_cache["quotes"]
        main.HOME_LIVE_CACHE["marketUpdatedEpoch"] = old_cache["marketUpdatedEpoch"]
        main.HOME_LIVE_CACHE["quoteUpdatedEpoch"] = old_cache["quoteUpdatedEpoch"]


def test_individually_refreshed_quote_can_be_reused(monkeypatch):
    old_cache = {
        "quotes": dict(main.HOME_LIVE_CACHE.get("quotes") or {}),
        "marketUpdatedEpoch": dict(main.HOME_LIVE_CACHE.get("marketUpdatedEpoch") or {}),
        "quoteUpdatedEpoch": dict(main.HOME_LIVE_CACHE.get("quoteUpdatedEpoch") or {}),
    }
    try:
        main.HOME_LIVE_CACHE["quotes"] = {
            "000660.KS": {
                "ticker": "000660.KS",
                "price": 1800000,
                "change": -3.5,
                "asOf": "2026-09-28T15:30:00+09:00",
            }
        }
        main.HOME_LIVE_CACHE["marketUpdatedEpoch"] = {"KR": 0.0, "US": 0.0}
        main.HOME_LIVE_CACHE["quoteUpdatedEpoch"] = {"000660.KS": time.time()}
        monkeypatch.setattr(main, "_open_home_markets", lambda *_args, **_kwargs: {"KR": ["000660.KS"]})
        monkeypatch.setattr(main, "fetch_quote_snapshot", lambda _ticker: (_ for _ in ()).throw(AssertionError("provider should not run")))

        payload = asyncio.run(main.quote_snapshots("000660.KS"))
        assert payload["sharedCacheHits"] == 1
        assert payload["providerFetches"] == 0
        assert payload["results"][0]["price"] == 1800000
    finally:
        main.HOME_LIVE_CACHE["quotes"] = old_cache["quotes"]
        main.HOME_LIVE_CACHE["marketUpdatedEpoch"] = old_cache["marketUpdatedEpoch"]
        main.HOME_LIVE_CACHE["quoteUpdatedEpoch"] = old_cache["quoteUpdatedEpoch"]


def test_first_home_activation_does_not_mark_seeded_market_fresh():
    source = inspect.getsource(main._home_live_worker)
    assert 'HOME_LIVE_CACHE["marketUpdatedEpoch"][market] = now' not in source
    assert "timeout = HOME_LIVE_FIRST_VISITOR_GRACE_SEC" in source
