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


def test_quality_keeps_cumulative_flows_separate_from_year_end_balances():
    rows = [
        _row("ifrs-full_Revenue", "매출액", thstrm_add_amount="110", frmtrm_add_amount="90"),
        _row("dart_OperatingIncomeLoss", "영업이익", thstrm_add_amount="15", frmtrm_add_amount="9"),
        _row("ifrs-full_ProfitLoss", "당기순이익", thstrm_amount="7", thstrm_add_amount="12", frmtrm_add_amount="8"),
        dict(_row("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름",
                  thstrm_amount="0", frmtrm_amount="20", frmtrm_nm="제55기 반기"), sj_div="CF"),
        dict(_row("ifrs-full_Inventories", "재고자산", thstrm_amount="35", frmtrm_amount="30"), sj_div="BS"),
        dict(_row("ifrs-full_Assets", "자산총계", thstrm_amount="200", frmtrm_amount="180"), sj_div="BS"),
        dict(_row("ifrs-full_Liabilities", "부채총계", thstrm_amount="100", frmtrm_amount="80"), sj_div="BS"),
        dict(_row("ifrs-full_Equity", "자본총계", thstrm_amount="100", frmtrm_amount="100"), sj_div="BS"),
    ]
    quality = service.parse_financial_statement(rows, 2026, "11012")["quality"]
    assert quality["current"]["netIncome"] == 12
    assert quality["current"]["operatingCashFlow"] == 0
    assert quality["previous"]["operatingCashFlow"] == 20
    assert quality["current"]["inventories"] == 35
    assert quality["balanceComparison"] == "previous_year_end"
    assert quality["current"]["receivables"] is None
    assert quality["accounts"]["inventories"]["statement"] == "BS"


def test_optional_accounts_fail_closed_without_breaking_existing_profit_history():
    rows = [_row("ifrs-full_Revenue", "매출액", thstrm_amount="100"),
            _row("dart_OperatingIncomeLoss", "영업이익", thstrm_amount="10")]
    duplicate = dict(_row("ifrs-full_Inventories", "재고자산", thstrm_amount="5"), sj_div="BS")
    rows += [duplicate, dict(duplicate),
             dict(_row("ifrs-full_Assets", "자산총계", thstrm_amount="20"), sj_div="BS", currency="USD"),
             dict(_row("ifrs-full_Liabilities", "부채총계", thstrm_amount="10"), sj_div="BS", rcept_no="20260310000001")]
    parsed = service.parse_financial_statement(rows, 2025, "11011")
    assert parsed["years"][0]["revenue"] == 100
    latest = parsed["quality"]["annual"][-1]
    assert latest["inventories"] is None
    assert latest["assets"] is None
    assert latest["liabilities"] is None


def test_interim_cashflow_year_end_and_three_month_income_are_not_yoy_flows():
    rows = [_row("ifrs-full_Revenue", "매출액", thstrm_add_amount="100"),
            _row("dart_OperatingIncomeLoss", "영업이익", thstrm_add_amount="10"),
            _row("ifrs-full_ProfitLoss", "당기순이익", thstrm_amount="5", frmtrm_q_amount="4"),
            dict(_row("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름",
                      thstrm_amount="8", frmtrm_amount="20", frmtrm_nm="제55기말"), sj_div="CF")]
    quality = service.parse_financial_statement(rows, 2026, "11012")["quality"]
    assert quality["current"]["netIncome"] is None
    assert quality["previous"]["operatingCashFlow"] is None


def test_parser_revision_wins_at_identical_report_receipts():
    base = {"annualReportYear": 2025, "annualSourceUrl": "x?rcpNo=20260310002820"}
    assert service._freshness(dict(base, schemaVersion=2)) > service._freshness(base)
    assert service._freshness(dict(base, schemaVersion=2, parserVersion=3)) > service._freshness(dict(base, schemaVersion=2))


def test_prior_interim_cashflow_field_wins_over_prior_annual_year_end():
    rows = [_row("ifrs-full_Revenue", "매출액", thstrm_add_amount="110"),
            _row("dart_OperatingIncomeLoss", "영업이익", thstrm_add_amount="15"),
            dict(_row("ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름",
                      thstrm_amount="80", frmtrm_amount="120", frmtrm_nm="제55기말",
                      frmtrm_q_amount="35", frmtrm_q_nm="제55기 반기"), sj_div="CF")]
    quality = service.parse_financial_statement(rows, 2026, "11012")["quality"]
    assert quality["previous"]["operatingCashFlow"] == 35
    assert quality["accounts"]["operatingCashFlow"]["previousInterimPeriod"] == "제55기 반기"


def test_partial_refresh_retains_validated_period_and_quality_without_mixing_basis():
    old = {"available": True, "basis": "CFS", "currency": "KRW", "schemaVersion": 2,
           "annual": [{"year": 2025}], "annualReportYear": 2025, "annualSourceUrl": "a",
           "interim": {"year": 2026, "quarter": 2}, "interimSourceUrl": "b",
           "quality": {"annual": [{"year": 2025}], "interim": {"year": 2026, "quarter": 2}}}
    partial = dict(old, interim=None, quality={"annual": [{"year": 2025}]})
    merged = service._merge_validated(old, partial)
    assert merged["interim"] == old["interim"]
    assert merged["quality"]["interim"] == old["quality"]["interim"]
    assert service._merge_validated(old, dict(partial, basis="OFS"))["interim"] is None
    assert service._merge_validated(old, {"available": False}) == old


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
