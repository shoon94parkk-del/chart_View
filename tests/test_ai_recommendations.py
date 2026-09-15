import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("ai_recommendations", Path("scripts/update_ai_recommendations.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def candidate(symbol, price, score, *, mismatch=False):
    return {
        "code": symbol[:6], "symbol": symbol, "name": symbol, "price": price, "previousClose": price - 10,
        "change1d": 1.01, "technicalScore": score, "above20": True, "above60": True, "aligned": True,
        "cross20": False, "volumeRatio": 2.0, "ret5": 4.0, "ret20": 10.0, "avgValue20": 1000000,
        "technicalBreakdown": {"chasePenalty": 0}, "priceValidation": {"status": "mismatch" if mismatch else "pending"},
    }


def test_daily_top3_excludes_price_mismatches_and_is_transparent():
    rows = [candidate(f"00000{i}.KS", 100 + i, 30 - i) for i in range(4)]
    rows.insert(0, candidate("999999.KS", 999, 30, mismatch=True))
    day = module.build_day({"tradeDate": "2026-09-15", "stocks": rows, "verification": {"priceMismatchCount": 1, "pricePendingCount": 4}})
    assert [pick["symbol"] for pick in day["top3"]] == ["000000.KS", "000001.KS", "000002.KS"]
    assert "제외" in day["status"]
    assert all("기술 점수" in pick["reason"] for pick in day["top3"])


def test_track_record_keeps_daily_entries_and_reprices_from_latest_screener():
    days = [{"tradeDate": "2026-09-12", "top3": [{"rank": 1, "symbol": "000001.KS", "code": "000001", "name": "테스트", "close": 100, "totalScore": 90, "grade": "대기", "reason": "근거"}]}]
    rows = module.refresh_records(days, {"tradeDate": "2026-09-15", "stocks": [{"symbol": "000001.KS", "price": 110}]}, [])
    assert len(rows) == 1
    assert rows[0]["returnPct"] == 10.0
    assert rows[0]["bestReturnPct"] == 10.0
    assert rows[0]["lastUpdatedTradeDate"] == "2026-09-15"
