from unittest.mock import patch
import json
from pathlib import Path

import dart_financial_service as service


def _row(account_id, account_nm, **amounts):
    return {"sj_div": "IS", "account_detail": "-", "account_id": account_id,
            "account_nm": account_nm, "rcept_no": "20260310002820", "currency": "KRW", **amounts}


def test_annual_uses_one_filing_for_three_comparable_years():
    rows = [
        _row("ifrs-full_Revenue", "매출액", thstrm_amount="300,000", frmtrm_amount="200,000", bfefrmtrm_amount="100,000"),
        _row("dart_OperatingIncomeLoss", "영업이익", thstrm_amount="30,000", frmtrm_amount="-5,000", bfefrmtrm_amount="10,000"),
    ]
    parsed = service.parse_financial_statement(rows, 2025, "11011")
    assert parsed["years"] == [
        {"year": 2023, "revenue": 100000, "operatingProfit": 10000},
        {"year": 2024, "revenue": 200000, "operatingProfit": -5000},
        {"year": 2025, "revenue": 300000, "operatingProfit": 30000},
    ]


def test_interim_uses_cumulative_not_three_month_amounts():
    rows = [
        _row("ifrs-full_Revenue", "매출액", thstrm_amount="40", thstrm_add_amount="110", frmtrm_q_amount="30", frmtrm_add_amount="90"),
        _row("dart_OperatingIncomeLoss", "영업이익", thstrm_amount="5", thstrm_add_amount="15", frmtrm_q_amount="2", frmtrm_add_amount="9"),
    ]
    parsed = service.parse_financial_statement(rows, 2026, "11012")
    assert (parsed["revenue"], parsed["priorRevenue"]) == (110, 90)
    assert (parsed["operatingProfit"], parsed["priorOperatingProfit"]) == (15, 9)


def test_dart_negative_formats_remain_negative():
    assert service._amount("△1,234") == -1234
    assert service._amount("(1,234)") == -1234


def test_ambiguous_or_mismatched_statement_fails_closed():
    revenue = _row("ifrs-full_Revenue", "매출액", thstrm_amount="100")
    profit = _row("dart_OperatingIncomeLoss", "영업이익", thstrm_amount="10")
    assert service.parse_financial_statement([revenue, dict(revenue), profit], 2025, "11011") is None
    assert service.parse_financial_statement([revenue, dict(profit, rcept_no="20260310000001")], 2025, "11011") is None


def test_unavailable_key_does_not_invent_financials():
    with patch.dict("os.environ", {"DART_API_KEY": ""}):
        result = service._collect("005930", "005930.KS")
    assert result["available"] is False
    assert result["reason"] == "api_key_unavailable"


def test_major_company_static_cache_serves_before_dart_network():
    payload = json.loads(Path(service.STATIC_PATH).read_text(encoding="utf-8"))
    assert len(payload["companies"]) >= 14
    for code, row in payload["companies"].items():
        assert row["available"] and row["stockCode"] == code
        assert row["annual"] and row["annualSourceUrl"].startswith("https://dart.fss.or.kr/")
    with service._LOCK:
        service._CACHE.pop("005930", None)
        service._REFRESHING.discard("005930")
    with patch.object(service, "_persistent", return_value=None), \
         patch.object(service._POOL, "submit") as submit:
        row = service.fetch_financial_history("005930.KS")
    assert row["available"] is True
    assert [item["year"] for item in row["annual"]] == [2023, 2024, 2025]
    assert submit.called
    with service._LOCK:
        service._CACHE.pop("005930", None)
        service._REFRESHING.discard("005930")
