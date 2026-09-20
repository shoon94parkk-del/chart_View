from scripts.generate_macro_cache import INDICATORS, transform_yoy


def test_pce_indicators_are_registered_with_expected_series():
    assert INDICATORS["PCEPI"]["feed"] == "dallaspce:pce"
    assert "transform" not in INDICATORS["PCEPI"]
    assert INDICATORS["PCETRIM12M159SFRBDAL"]["feed"] == "dallaspce:trimmed"


def test_yoy_transform_uses_same_month_previous_year():
    rows = [
        {"time": f"2025-{month:02d}-01", "value": 100.0}
        for month in range(1, 13)
    ]
    rows += [
        {"time": "2026-01-01", "value": 103.0},
        {"time": "2026-02-01", "value": 104.0},
    ]
    result = transform_yoy(rows)
    assert result[0] == {"time": "2026-01-01", "value": 3.0}
    assert result[1] == {"time": "2026-02-01", "value": 4.0}
