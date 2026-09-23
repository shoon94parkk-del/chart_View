import market_service as ms


def _daily(closes, timestamps=None, meta=None):
    timestamps = timestamps or list(range(1700000000, 1700000000 + 86400 * len(closes), 86400))
    return {"meta": meta or {"currency": "USD"}, "timestamp": timestamps, "indicators": {"quote": [{"close": closes}]}}


def test_snapshot_price_and_change_come_from_same_two_daily_bars(monkeypatch):
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: _daily([7650.50, 7764.70, 7764.64]))
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("^GSPC")
    assert row["price"] == 7764.64
    assert row["previousClose"] == 7764.70
    assert row["change"] == 0.0


def test_stale_intraday_percent_cannot_leak_into_stock_snapshot(monkeypatch):
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: _daily([661.50, 736.60]))
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("META")
    assert row["price"] == 736.60
    assert row["previousClose"] == 661.50
    assert row["change"] == round((736.60 - 661.50) / 661.50 * 100, 2)


def test_weekend_or_holiday_uses_last_two_actual_bars(monkeypatch):
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: _daily([100.0, None, 101.0]))
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("TEST")
    assert row["price"] == 101.0
    assert row["previousClose"] == 100.0
    assert row["change"] == 1.0
