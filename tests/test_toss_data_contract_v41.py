from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")


def test_compare_exposes_explicit_basis():
    assert '"comparisonBasis"' in SOURCE
    assert '"currencyMode": "local currency per symbol; no FX conversion"' in SOURCE
    assert '"missingObservationPolicy": "missing observations are omitted; no interpolation"' in SOURCE
    assert '"totalReturnVerified": False' in SOURCE


def test_quote_endpoint_has_timestamp_currency_and_missing_value_contract():
    assert '@app.get("/api/quotes")' in SOURCE
    assert '"change": "percent change versus previous trading close"' in SOURCE
    assert '"asOf": "provider market timestamp when available"' in SOURCE
    assert '"currency": "provider currency"' in SOURCE
    assert '"missingValue": "null/omitted; zero is not used as a missing-value substitute"' in SOURCE


def test_macro_exposes_units_and_neutral_summary():
    assert "MACRO_DISPLAY_META" in SOURCE
    assert '"T10Y2Y": {"unit": "%p", "changeUnit": "bp"' in SOURCE
    assert '"PCEPI": {"unit": "% YoY", "changeUnit": "bp"' in SOURCE
    assert '"PCETRIM12M159SFRBDAL": {"unit": "% YoY", "changeUnit": "bp"' in SOURCE
    assert "시장 환경을 설명하기 위한 요약이며 투자 행동을 권유하지 않습니다." in SOURCE
    assert "방어적 포지션을 고려하세요" not in SOURCE
    assert "선별적 접근과 모니터링이 필요합니다" not in SOURCE
