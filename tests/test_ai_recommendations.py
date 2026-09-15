import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("ai_recommendations", Path("scripts/update_ai_recommendations.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def reviewed_day():
    return {
        "tradeDate": "2026-09-15",
        "analysis": {"sourceType": "gpt_screener_review", "status": "complete", "model": "GPT", "candidateTradeDate": "2026-09-15"},
        "top3": [{"rank": 1, "symbol": "000001.KS", "code": "000001", "name": "테스트", "close": 100, "totalScore": 90, "grade": "A", "reason": "기업 성장 근거와 리스크"}] * 3,
    }


def test_only_completed_gpt_review_can_enter_track_record():
    day = reviewed_day()
    assert module.is_gpt_reviewed_day(day)
    day["analysis"]["sourceType"] = "technical_screener"
    assert not module.is_gpt_reviewed_day(day)


def test_track_record_reprices_only_gpt_reviewed_days():
    day = reviewed_day()
    day["top3"] = [{"rank": 1, "symbol": "000001.KS", "code": "000001", "name": "테스트", "close": 100, "totalScore": 90, "grade": "A", "reason": "근거"}, {"rank": 2, "symbol": "000002.KS", "code": "000002", "name": "제외", "close": 100, "totalScore": 80, "grade": "B", "reason": "근거"}, {"rank": 3, "symbol": "000003.KS", "code": "000003", "name": "제외", "close": 100, "totalScore": 70, "grade": "B", "reason": "근거"}]
    technical_only = {"tradeDate": "2026-09-16", "analysis": {"sourceType": "technical_screener"}, "top3": day["top3"]}
    rows = module.refresh_records([day, technical_only], {"tradeDate": "2026-09-16", "stocks": [{"symbol": "000001.KS", "price": 110}]}, [])
    assert len(rows) == 3
    assert rows[0]["returnPct"] == 10.0
    assert rows[0]["analysisSource"] == "GPT 스크리너 재분석"
