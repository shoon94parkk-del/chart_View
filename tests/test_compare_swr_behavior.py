import time

import market_service as market


def _stale_key(symbol="AAPL", period="1mo"):
    interval, key = market._compare_request_parts(symbol, period, None, None)
    return interval, key


def test_stale_compare_returns_immediately_and_schedules_refresh(monkeypatch):
    market._compare_cache.clear()
    market._compare_refreshing.clear()
    _, key = _stale_key()
    cached = {"ticker": "AAPL", "data": [{"time": 1, "value": 0.0}]}
    market._compare_cache[key] = (time.time() - market.COMPARE_CACHE_FRESH_TTL_SECONDS - 1, cached)

    scheduled = []

    def schedule(*args):
        scheduled.append(args)

    def foreground_provider(*args, **kwargs):
        raise AssertionError("stale cache must not call the provider on the request path")

    monkeypatch.setattr(market, "_schedule_compare_refresh", schedule)
    monkeypatch.setattr(market, "_load_compare_stock", foreground_provider)

    result = market.fetch_compare_stock("AAPL", "1mo", None, None)

    assert result is cached
    assert len(scheduled) == 1
    assert scheduled[0][0] == key


def test_failed_background_refresh_keeps_last_good_compare(monkeypatch):
    market._compare_cache.clear()
    market._compare_refreshing.clear()
    interval, key = _stale_key("NVDA")
    cached = {"ticker": "NVDA", "data": [{"time": 1, "value": 0.0}]}
    original_timestamp = time.time() - 999
    market._compare_cache[key] = (original_timestamp, cached)
    market._compare_refreshing.add(key)

    monkeypatch.setattr(market, "_load_compare_stock", lambda *args, **kwargs: None)

    market._refresh_compare_cache(key, "NVDA", "1mo", None, None, interval)

    assert market._compare_cache[key] == (original_timestamp, cached)
    assert key not in market._compare_refreshing


def test_compare_cache_peek_returns_good_value_without_provider(monkeypatch):
    market._compare_cache.clear()
    market._compare_refreshing.clear()
    _, key = _stale_key("AAPL")
    cached = {"ticker": "AAPL", "data": [{"time": 1, "value": 0.0}]}
    market._compare_cache[key] = (time.time(), cached)

    monkeypatch.setattr(
        market,
        "_load_compare_stock",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("peek must not call provider")),
    )

    hit, value = market.get_compare_cache("AAPL", "1mo", None, None)

    assert hit is True
    assert value is cached
