import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("ai_recommendations", Path("scripts/update_ai_recommendations.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def reviewed_day():
    return {
        "tradeDate": "2026-09-15",
        "analysis": {"sourceType": "gpt_screener_review", "status": "complete", "model": "GPT", "candidateTradeDate": "2026-09-15"},
        "top3": [{"rank": 1, "symbol": "000001.KS", "code": "000001", "name": "테스트", "close": 100, "totalScore": 90, "grade": "A", "reason": "기업 성장 근거와 리스크"}] * 3,
    }


def three_pick_day(trade_date="2026-09-15"):
    day = reviewed_day()
    day["tradeDate"] = trade_date
    day["analysis"]["candidateTradeDate"] = trade_date
    day["top3"] = [
        {"rank": 1, "symbol": "000001.KS", "code": "000001", "name": "테스트1", "close": 100, "totalScore": 90, "grade": "A", "reason": "근거"},
        {"rank": 2, "symbol": "000002.KS", "code": "000002", "name": "테스트2", "close": 200, "totalScore": 80, "grade": "B", "reason": "근거"},
        {"rank": 3, "symbol": "000003.KS", "code": "000003", "name": "테스트3", "close": 300, "totalScore": 70, "grade": "B", "reason": "근거"},
    ]
    return day


def screener(trade_date="2026-09-16", first_price=110):
    return {
        "tradeDate": trade_date,
        "stocks": [
            {"symbol": "000001.KS", "code": "000001", "name": "테스트1", "price": first_price},
            {"symbol": "000002.KS", "code": "000002", "name": "테스트2", "price": 210},
            {"symbol": "000003.KS", "code": "000003", "name": "테스트3", "price": 330},
        ],
    }


def test_only_completed_gpt_review_can_enter_track_record():
    day = reviewed_day()
    assert module.is_gpt_reviewed_day(day)
    day["analysis"]["sourceType"] = "technical_screener"
    assert not module.is_gpt_reviewed_day(day)


def test_track_record_reprices_only_gpt_reviewed_days():
    day = three_pick_day()
    technical_only = {"tradeDate": "2026-09-16", "analysis": {"sourceType": "technical_screener"}, "top3": day["top3"]}
    rows = module.refresh_records([day, technical_only], screener(), [])
    assert len(rows) == 3
    assert rows[0]["returnPct"] == 10.0
    assert rows[0]["analysisSource"] == "GPT 스크리너 재분석"


def test_user_final_selection_is_a_publishable_track_record_day():
    day = three_pick_day()
    day["analysis"] = {
        "sourceType": "user_final_selection",
        "status": "complete",
        "model": "GPT-5.6 Sol",
        "candidateTradeDate": day["tradeDate"],
    }
    rows = module.refresh_records([day], screener(), [])
    assert len(rows) == 3
    assert rows[0]["returnPct"] == 10.0
    assert rows[0]["analysisSource"] == "사용자 최종 선택"


def test_existing_legacy_pick_day_is_repriced_and_metadata_is_preserved():
    day = three_pick_day()
    day.pop("analysis")
    existing = [
        {
            "recommendedDate": "2026-09-15",
            "rank": pick["rank"],
            "symbol": pick["symbol"],
            "code": pick["code"],
            "name": pick["name"],
            "recommendedPrice": pick["close"],
            "currentPrice": pick["close"],
            "returnPct": 0.0,
            "bestReturnPct": 0.0,
            "lastUpdatedTradeDate": "2026-09-15",
            "grade": "기존 등급",
            "reason": "기존 상세 사유",
            "score": 77,
            "analysisSource": "기존 공개 기록",
        }
        for pick in day["top3"]
    ]
    rows = module.refresh_records([day], screener(), existing)
    assert len(rows) == 3
    assert rows[0]["currentPrice"] == 110
    assert rows[0]["returnPct"] == 10.0
    assert rows[0]["lastUpdatedTradeDate"] == "2026-09-16"
    assert rows[0]["reason"] == "기존 상세 사유"
    assert rows[0]["grade"] == "기존 등급"
    assert rows[0]["score"] == 77
    assert rows[0]["analysisSource"] == "기존 공개 기록"


def test_same_day_recommendation_always_starts_at_zero_return():
    day = three_pick_day("2026-09-16")
    rows = module.refresh_records([day], screener("2026-09-16", first_price=999), [])
    assert rows[0]["recommendedPrice"] == 100
    assert rows[0]["currentPrice"] == 100
    assert rows[0]["returnPct"] == 0.0


def test_name_symbol_identity_mismatch_blocks_return_calculation():
    day = three_pick_day("2026-09-16")
    day["top3"][0]["name"] = "글로벌텍스프리"
    bad_screener = screener("2026-09-16")
    bad_screener["stocks"][0]["name"] = "제이앤티씨"
    bad_screener["stocks"].append({"symbol": "204620.KQ", "code": "204620", "name": "글로벌텍스프리", "price": 5880})

    with pytest.raises(ValueError, match="identity mismatch") as exc:
        module.refresh_records([day], bad_screener, [])
    assert "204620.KQ" in str(exc.value)
