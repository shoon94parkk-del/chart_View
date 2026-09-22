import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("validate_ai_rankings", Path("scripts/validate_ai_rankings.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def valid_day(symbol="204620.KQ", code="204620", name="글로벌텍스프리"):
    base = {
        "analysis": {"sourceType": "gpt_screener_review", "status": "complete", "model": "GPT", "candidateTradeDate": "2026-09-16"},
        "tradeDate": "2026-09-16",
        "scorePolicy": {"weights": {"companyGrowth": 35, "technical": 30}},
    }
    scores = {"industryScore": 15, "companyScore": 35, "valuationScore": 8, "catalystRiskScore": 8, "technicalScore": 26}
    base["top3"] = [
        {"rank": 1, "symbol": symbol, "code": code, "name": name, "close": 5880, "reason": "근거", "totalScore": 92, **scores},
        {"rank": 2, "symbol": "000001.KS", "code": "000001", "name": "테스트1", "close": 100, "reason": "근거", "totalScore": 92, **scores},
        {"rank": 3, "symbol": "000002.KS", "code": "000002", "name": "테스트2", "close": 100, "reason": "근거", "totalScore": 92, **scores},
    ]
    return base


def identity_index():
    return module.build_identity_index({"stocks": [
        {"symbol": "204620.KQ", "name": "글로벌텍스프리"},
        {"symbol": "204270.KQ", "name": "제이앤티씨"},
        {"symbol": "000001.KS", "name": "테스트1"},
        {"symbol": "000002.KS", "name": "테스트2"},
    ]})


def test_valid_identity_passes():
    by_symbol, by_name = identity_index()
    assert module.validate(valid_day(), by_symbol, by_name) == []


def test_wrong_symbol_for_name_is_rejected_with_expected_symbol():
    by_symbol, by_name = identity_index()
    errors = module.validate(valid_day(symbol="204270.KQ", code="204270"), by_symbol, by_name)
    assert any("identity mismatch" in error for error in errors)
    assert any("expected=204620.KQ" in error for error in errors)


def test_user_final_selection_allows_two_corrected_picks():
    by_symbol, by_name = identity_index()
    day = valid_day()
    day["analysis"] = {
        "sourceType": "user_final_selection",
        "status": "complete",
        "model": "GPT-5.6 Sol",
        "candidateTradeDate": day["tradeDate"],
    }
    day["top3"] = day["top3"][:2]
    for pick in day["top3"]:
        pick.pop("industryScore", None)
        pick.pop("companyScore", None)
        pick.pop("valuationScore", None)
        pick.pop("catalystRiskScore", None)
        pick.pop("technicalScore", None)
    assert module.validate(day, by_symbol, by_name) == []
