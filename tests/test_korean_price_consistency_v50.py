from types import SimpleNamespace

import realtime_korea


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def reset_quote_cache():
    with realtime_korea._quote_lock:
        realtime_korea._quote_cache.clear()


def test_korean_stock_price_is_identical_across_quote_compare_and_valuation(monkeypatch):
    reset_quote_cache()
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append((url, kwargs.get("params")))
        assert url.endswith("/api/stock/000660/basic")
        return FakeResponse({
            "stockName": "SK하이닉스",
            "closePrice": "777,000",
            "fluctuationsRatio": "1.23",
            "localTradedAt": "2026-09-14T15:10:00+09:00",
            "marketStatus": "OPEN",
            "delayTime": 0,
        })

    monkeypatch.setattr(realtime_korea.requests, "get", fake_get)

    module = SimpleNamespace(
        fetch_quote_snapshot=lambda symbol: {
            "ticker": symbol, "price": 770000, "change": 0.5, "source": "Yahoo Chart 5m"
        },
        fetch_compare_stock=lambda symbol, period="1mo", start=None, end=None: {
            "ticker": symbol, "name": "SK하이닉스", "price": 771000, "return": 4.2,
            "data": [{"time": 1, "value": 0}, {"time": 2, "value": 4.2}],
            "currency": "KRW", "source": "Yahoo Chart", "priceBasis": "adjusted_close",
            "requestedPeriod": period, "startDate": "2026-08-14", "endDate": "2026-09-14",
            "observations": 2,
        },
        fetch_valuation_snapshot=lambda symbol: {
            "ticker": symbol, "price": 772000, "currency": "KRW",
            "dataSource": "Yahoo Chart + Fundamentals",
            "fieldMeta": {"price": {"source": "Yahoo Chart"}},
        },
    )

    realtime_korea.install_patch(module)

    quote = module.fetch_quote_snapshot("000660.KS")
    compare = module.fetch_compare_stock("000660.KS", "1mo")
    valuation = module.fetch_valuation_snapshot("000660.KS")

    assert quote["price"] == 777000
    assert compare["price"] == 777000
    assert valuation["price"] == 777000
    assert quote["source"].startswith("Naver Finance")
    assert compare["quoteSource"].startswith("Naver Finance")
    assert valuation["fieldMeta"]["price"]["source"].startswith("Naver Finance")
    # One Naver call is shared by all three surfaces during the short consistency window.
    assert len(calls) == 1


def test_korean_stock_basic_failure_uses_realtime_polling(monkeypatch):
    reset_quote_cache()

    def fake_get(url, *args, **kwargs):
        if "/api/stock/005930/basic" in url:
            return FakeResponse({}, status=503)
        assert url == "https://polling.finance.naver.com/api/realtime"
        assert kwargs["params"]["query"] == "SERVICE_ITEM:005930"
        return FakeResponse({
            "result": {"areas": [{"datas": [{
                "nm": "삼성전자", "nv": 266000, "cr": 2.1, "ms": "OPEN"
            }]}]}
        })

    monkeypatch.setattr(realtime_korea.requests, "get", fake_get)
    quote = realtime_korea.fetch_korean_stock_quote("005930.KS")

    assert quote["price"] == 266000
    assert quote["change"] == 2.1
    assert quote["source"] == "Naver Finance realtime polling"


def test_non_korean_symbols_keep_original_provider(monkeypatch):
    reset_quote_cache()
    monkeypatch.setattr(
        realtime_korea.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Naver must not be called")),
    )
    module = SimpleNamespace(
        fetch_quote_snapshot=lambda symbol: {"ticker": symbol, "price": 200, "source": "Yahoo"},
        fetch_compare_stock=lambda symbol, *args, **kwargs: {"ticker": symbol, "price": 201, "source": "Yahoo"},
        fetch_valuation_snapshot=lambda symbol: {"ticker": symbol, "price": 202, "dataSource": "Yahoo"},
    )
    realtime_korea.install_patch(module)

    assert module.fetch_quote_snapshot("NVDA")["price"] == 200
    assert module.fetch_compare_stock("NVDA")["price"] == 201
    assert module.fetch_valuation_snapshot("NVDA")["price"] == 202
