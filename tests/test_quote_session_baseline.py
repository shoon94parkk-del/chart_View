from datetime import datetime
from zoneinfo import ZoneInfo

import market_service as ms


ET = ZoneInfo("America/New_York")


def _chart(rows, *, tz="America/New_York", currency="USD"):
    return {
        "meta": {"currency": currency, "exchangeTimezoneName": tz},
        "timestamp": [int(dt.timestamp()) for dt, _ in rows],
        "indicators": {"quote": [{"close": [px for _, px in rows]}]},
    }


def _dt(y, m, d, h=15, minute=55):
    return datetime(y, m, d, h, minute, tzinfo=ET)


def test_sp500_uses_adjacent_actual_regular_sessions(monkeypatch):
    data = _chart([
        (_dt(2026, 9, 21), 7764.70),
        (_dt(2026, 9, 22), 7764.64),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: data)
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("^GSPC")
    assert row["price"] == 7764.64
    assert row["previousClose"] == 7764.70
    assert row["change"] == 0.0
    assert row["sessionDate"] == "2026-09-22"
    assert row["previousSessionDate"] == "2026-09-21"
    assert "5m regular-session" in row["source"]


def test_meta_does_not_reuse_prior_sessions_large_gain(monkeypatch):
    data = _chart([
        (_dt(2026, 9, 18), 665.73),
        (_dt(2026, 9, 21), 741.24),
        (_dt(2026, 9, 22), 736.60),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: data)
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("META")
    assert row["price"] == 736.60
    assert row["previousClose"] == 741.24
    assert row["change"] == -0.63


def test_open_session_compares_partial_current_price_to_prior_close(monkeypatch):
    data = _chart([
        (_dt(2026, 9, 22), 736.60),
        (datetime(2026, 9, 23, 10, 5, tzinfo=ET), 742.41),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: data)
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("META")
    assert row["price"] == 742.41
    assert row["previousClose"] == 736.60
    assert row["change"] == 0.79


def test_weekend_or_holiday_groups_actual_session_dates(monkeypatch):
    data = _chart([
        (_dt(2026, 9, 18), 100.0),
        (_dt(2026, 9, 21), 101.0),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: data)
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("TEST")
    assert row["previousClose"] == 100.0
    assert row["price"] == 101.0
    assert row["change"] == 1.0


def test_continuous_asset_uses_daily_fallback(monkeypatch):
    daily = _chart([
        (_dt(2026, 9, 21), 90.50),
        (_dt(2026, 9, 22), 90.02),
    ])
    monkeypatch.setattr(ms, "_chart_result", lambda *a, **k: daily)
    ms._quote_cache.clear()
    row = ms.fetch_quote_snapshot("CL=F")
    assert row["price"] == 90.02
    assert row["previousClose"] == 90.50
    assert row["change"] == round((90.02 - 90.50) / 90.50 * 100, 2)
    assert "daily atomic" in row["source"]
