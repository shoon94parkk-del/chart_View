import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_home_snapshot_v67",
    ROOT / "scripts" / "generate_home_snapshot.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_us_snapshot_uses_last_two_daily_closes_not_5d_meta_baseline(monkeypatch):
    def fake_get(url, **kwargs):
        assert "NVDA" in url
        assert kwargs["params"]["range"] == "5d"
        return FakeResponse({
            "chart": {
                "result": [{
                    "meta": {
                        "shortName": "NVIDIA Corporation",
                        "regularMarketPrice": 227.38,
                        # Deliberately a 5D-like baseline. V67 must ignore it.
                        "previousClose": 210.96,
                        "chartPreviousClose": 210.96,
                        "regularMarketTime": 1789992000,
                    },
                    "indicators": {
                        "quote": [{
                            "close": [210.96, 214.10, 220.00, 222.27, 227.38]
                        }]
                    },
                }]
            }
        })

    monkeypatch.setattr(module.requests, "get", fake_get)
    row = module._fetch_yahoo_daily("NVDA")

    expected = (227.38 - 222.27) / 222.27 * 100
    wrong_5d = (227.38 - 210.96) / 210.96 * 100
    assert abs(row["change"] - expected) < 0.001
    assert abs(row["change"] - wrong_5d) > 1
    assert row["source"] == "Yahoo daily close"


def test_korean_snapshot_uses_naver_fluctuation_ratio(monkeypatch):
    def fake_get(url, **kwargs):
        assert "/api/stock/005930/basic" in url
        return FakeResponse({
            "stockName": "삼성전자",
            "closePrice": "276,500",
            "fluctuationsRatio": "1.25",
            "localTradedAt": "2026-09-22T15:30:00+09:00",
        })

    monkeypatch.setattr(module.requests, "get", fake_get)
    row = module.fetch("005930.KS")

    assert row["price"] == 276500
    assert row["change"] == 1.25
    assert row["source"] == "Naver Finance KRX/Koscom"


def test_main_binds_realtime_patch_before_market_helpers():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    patch_at = source.index("_install_korea_realtime(_market_service)")
    quote_alias_at = source.index("fetch_quote_snapshot = _market_service.fetch_quote_snapshot")
    assert patch_at < quote_alias_at
