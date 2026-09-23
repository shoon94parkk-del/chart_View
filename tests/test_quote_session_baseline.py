import market_service as ms


def _chart(meta, closes):
    return {"meta": meta, "indicators": {"quote": [{"close": closes}]}}


def test_us_premarket_change_uses_last_completed_regular_close(monkeypatch):
    calls = iter([
        _chart({"regularMarketPrice": 668.0, "regularMarketTime": 1790179200, "currency": "USD", "chartPreviousClose": 600.0}, [668.0]),
        _chart({"regularMarketPrice": 661.5, "previousClose": 736.6}, [650.0, 736.6]),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *args, **kwargs: next(calls))
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("META")
    assert row["price"] == 668.0
    assert row["change"] == round((668.0 - 736.6) / 736.6 * 100, 2)
    assert row["change"] < 0


def test_completed_session_uses_preceding_daily_close(monkeypatch):
    calls = iter([
        _chart({"regularMarketPrice": 736.6, "regularMarketTime": 1790179200, "currency": "USD"}, [736.6]),
        _chart({"regularMarketPrice": 736.6}, [661.5, 736.6]),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *args, **kwargs: next(calls))
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("META")
    assert row["change"] == round((736.6 - 661.5) / 661.5 * 100, 2)
