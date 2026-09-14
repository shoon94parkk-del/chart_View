from types import SimpleNamespace

import realtime_korea as rk


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_basic_kospi_quote_parses_realtime_fields(monkeypatch):
    payload = {
        "closePrice": "6,955.42",
        "fluctuationsRatio": "0.66",
        "localTradedAt": "2026-09-14T10:41:02+09:00",
        "marketStatus": "OPEN",
        "delayTime": 0,
    }
    monkeypatch.setattr(rk.requests, "get", lambda *args, **kwargs: FakeResponse(payload))
    row = rk.fetch_korean_index_quote("^KS11")
    assert row["price"] == 6955.42
    assert row["change"] == 0.66
    assert row["marketStatus"] == "OPEN"
    assert row["delayTime"] == 0
    assert row["source"].startswith("Naver Finance")


def test_patch_only_overrides_korean_indices(monkeypatch):
    calls = []

    def original(symbol):
        calls.append(symbol)
        return {"ticker": symbol, "source": "Yahoo"}

    module = SimpleNamespace(fetch_quote_snapshot=original)
    monkeypatch.setattr(rk, "fetch_korean_index_quote", lambda symbol: {"ticker": symbol, "source": "Naver"})
    rk.install_patch(module)

    assert module.fetch_quote_snapshot("^KS11")["source"] == "Naver"
    assert module.fetch_quote_snapshot("AAPL")["source"] == "Yahoo"
    assert calls == ["AAPL"]


def test_naver_failure_falls_back_to_existing_provider(monkeypatch):
    def original(symbol):
        return {"ticker": symbol, "source": "Yahoo"}

    module = SimpleNamespace(fetch_quote_snapshot=original)
    monkeypatch.setattr(rk, "fetch_korean_index_quote", lambda symbol: (_ for _ in ()).throw(RuntimeError("down")))
    rk.install_patch(module)
    assert module.fetch_quote_snapshot("^KQ11")["source"] == "Yahoo"
