from datetime import datetime

import pytest

import export_momentum_service as export_service


def test_service_key_accepts_existing_render_name_and_decodes_once(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    monkeypatch.delenv("CUSTOMS_API_KEY", raising=False)
    monkeypatch.setenv("CUSTOMS_TOTAL_API_KEY", "abc%2B123%2Fxyz%3D%3D")
    assert export_service.service_key() == "abc+123/xyz=="


def test_parse_xml_payload_reads_items_and_rejects_auth_error():
    ok = b"""<?xml version="1.0" encoding="UTF-8"?>
    <response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
    <body><items><item><year>2026.09</year><expDlr>123</expDlr></item></items></body></response>"""
    rows = export_service._parse_xml_payload(ok)
    assert rows == [{"year": "2026.09", "expDlr": "123"}]

    denied = b"""<OpenAPI_ServiceResponse><cmmMsgHeader>
      <returnReasonCode>20</returnReasonCode>
      <returnAuthMsg>SERVICE_ACCESS_DENIED_ERROR</returnAuthMsg>
    </cmmMsgHeader></OpenAPI_ServiceResponse>"""
    with pytest.raises(export_service.CustomsApiError):
        export_service._parse_xml_payload(denied)


def test_country_aggregation_uses_shortest_hs_level_to_avoid_double_count():
    rows = [
        {"year": "2026.09", "hsCd": "85", "expDlr": "100"},
        {"year": "2026.09", "hsCd": "87", "expDlr": "50"},
        {"year": "2026.09", "hsCd": "8542", "expDlr": "80"},
        {"year": "2026.09", "hsCd": "8703", "expDlr": "40"},
        {"year": "2026.08", "hsCd": "85", "expDlr": "999"},
    ]
    assert export_service._country_export(rows, "202609") == 150


def test_hs_prefix_export_accepts_itemtrade_hs_code_and_prefers_aggregate():
    rows = [
        {"year": "2026.09", "hsCode": "85", "expDlr": "500"},
        {"year": "2026.09", "hsCode": "8541", "expDlr": "120"},
        {"year": "2026.09", "hsCode": "8542", "expDlr": "300"},
        {"year": "2026.09", "hsCode": "8542310000", "expDlr": "250"},
    ]
    assert export_service._hs_prefix_export(rows, "8542", "202609") == 300


def test_hs_weight_and_unit_value_are_derived_from_official_weight_fields():
    current = [
        {"year": "2026.08", "hsCode": "3304", "expDlr": "1200", "expWgt": "100"},
        {"year": "2026.08", "hsCode": "3304991000", "expDlr": "900", "expWgt": "70"},
    ]
    prior = [
        {"year": "2025.08", "hsCode": "3304", "expDlr": "1000", "expWgt": "100"},
    ]
    assert export_service._hs_prefix_weight(current, "3304", "202608") == 100
    assert export_service._unit_value_usd_per_kg(1200, 100) == 12
    rows = export_service._build_items_from_rows(current, prior, "202608")
    cosmetic = next(row for row in rows if row["name"] == "화장품")
    assert cosmetic["exportWeightKg"] == 100
    assert cosmetic["exportWeightYoY"] == 0.0
    assert cosmetic["unitValueUsdPerKg"] == 12
    assert cosmetic["unitValueYoY"] == 20.0


def test_unit_value_is_missing_when_weight_is_zero_or_absent():
    assert export_service._unit_value_usd_per_kg(1000, 0) is None
    assert export_service._unit_value_usd_per_kg(1000, None) is None


def test_item_snapshot_includes_imports_and_trade_balance():
    current = [
        {
            "year": "2026.08", "hsCode": "3304",
            "expDlr": "1200000000", "expWgt": "100000000",
            "impDlr": "500000000", "impWgt": "40000000", "balPayments": "700000000",
        },
    ]
    prior = [
        {
            "year": "2025.08", "hsCode": "3304",
            "expDlr": "1000000000", "expWgt": "100000000",
            "impDlr": "400000000", "impWgt": "35000000", "balPayments": "600000000",
        },
    ]
    rows = export_service._build_items_from_rows(current, prior, "202608")
    cosmetic = next(row for row in rows if row["key"] == "cosmetics")
    assert cosmetic["importsUsdBillion"] == pytest.approx(0.5)
    assert cosmetic["importYoY"] == 25.0
    assert cosmetic["importWeightKg"] == 40_000_000
    assert cosmetic["tradeBalanceUsdBillion"] == pytest.approx(0.7)


def test_group_history_builds_12_month_value_volume_unit_value(monkeypatch):
    group = next(row for row in export_service.ITEM_GROUPS if row["key"] == "cosmetics")

    def fake_range(_group, start, end):
        rows = {}
        period = start
        while period <= end:
            year = int(period[:4])
            month = int(period[4:])
            amount = (1000 + month * 10) * (1.10 if year == 2026 else 1.0)
            weight = 100 + month
            rows.setdefault("3304", []).append({
                "year": f"{year}.{month:02d}",
                "hsCode": "3304",
                "expDlr": str(amount),
                "expWgt": str(weight),
                "impDlr": str(amount * 0.4),
                "impWgt": str(weight * 0.5),
                "balPayments": str(amount * 0.6),
            })
            period = export_service._month_shift(period, 1)
        return rows

    monkeypatch.setattr(export_service, "_fetch_group_range", fake_range)
    history = export_service._build_group_history(group, "202608")
    assert len(history) == 12
    assert history[-1]["period"] == "2026-08"
    assert history[-1]["exportsUsdBillion"] is not None
    assert history[-1]["exportWeightKg"] is not None
    assert history[-1]["unitValueUsdPerKg"] is not None
    assert history[-1]["importsUsdBillion"] is not None
    assert history[-1]["tradeBalanceUsdBillion"] is not None


def test_country_item_breakdown_reports_configured_market_share(monkeypatch):
    group = next(row for row in export_service.ITEM_GROUPS if row["key"] == "cosmetics")

    values = {"US": 300, "CN": 200, "VN": 100, "JP": 50, "TW": 25}
    def fake_country(country, _group, _period):
        value = values[country["code"]]
        return {"name": country["name"], "code": country["code"], "exportsUsdBillion": value / 1_000_000_000}

    monkeypatch.setattr(export_service, "_fetch_country_item_export", fake_country)
    rows = export_service._build_country_item_breakdown(group, "202608", 1000)
    assert len(rows) == 5
    us = next(row for row in rows if row["code"] == "US")
    assert us["sharePct"] == 30.0


def test_hs2_breadth_counts_growth_and_ranks_change_contributors():
    current = [
        {"year": "2026.08", "hsCode": "85", "statKor": "전기기기", "expDlr": "1500000000"},
        {"year": "2026.08", "hsCode": "87", "statKor": "자동차", "expDlr": "700000000"},
        {"year": "2026.08", "hsCode": "72", "statKor": "철강", "expDlr": "300000000"},
    ]
    prior = [
        {"year": "2025.08", "hsCode": "85", "statKor": "전기기기", "expDlr": "1000000000"},
        {"year": "2025.08", "hsCode": "87", "statKor": "자동차", "expDlr": "800000000"},
        {"year": "2025.08", "hsCode": "72", "statKor": "철강", "expDlr": "300000000"},
    ]
    breadth = export_service._build_hs2_breadth(current, prior, "202608")
    assert breadth["comparableCount"] == 3
    assert breadth["risingCount"] == 1
    assert breadth["fallingCount"] == 1
    assert breadth["flatCount"] == 1
    assert breadth["risingBreadthPct"] == pytest.approx(33.3)
    assert breadth["topPositive"][0]["code"] == "85"
    assert breadth["topPositive"][0]["deltaUsdBillion"] == pytest.approx(0.5)
    assert breadth["topNegative"][0]["code"] == "87"
    assert breadth["topNegative"][0]["deltaUsdBillion"] == pytest.approx(-0.1)


def test_momentum_summary_compares_latest_three_months_with_previous_three():
    history = [
        {"period": "2026-03", "exportYoY": 2, "exportWeightYoY": -4, "unitValueYoY": 6},
        {"period": "2026-04", "exportYoY": 4, "exportWeightYoY": -2, "unitValueYoY": 7},
        {"period": "2026-05", "exportYoY": 6, "exportWeightYoY": 0, "unitValueYoY": 8},
        {"period": "2026-06", "exportYoY": 8, "exportWeightYoY": 2, "unitValueYoY": 9},
        {"period": "2026-07", "exportYoY": 10, "exportWeightYoY": 4, "unitValueYoY": 10},
        {"period": "2026-08", "exportYoY": 12, "exportWeightYoY": 6, "unitValueYoY": 11},
    ]
    momentum = export_service._build_momentum_summary(history)
    assert momentum["exports"]["avg3mYoY"] == 10.0
    assert momentum["exports"]["previous3mYoY"] == 4.0
    assert momentum["exports"]["accelerationPp"] == 6.0
    assert momentum["exports"]["label"] == "증가세 강화"
    assert momentum["latestPhase"] == "물량↑·단위가치↑"
    assert len(momentum["phaseHistory"]) == 6


def test_semiconductor_breakdown_reuses_monthly_rows_without_provider_calls(monkeypatch):
    def fail_provider(*_args, **_kwargs):
        raise AssertionError("semiconductor breakdown must not add provider calls")
    monkeypatch.setattr(export_service, "_fetch_item_range_rows", fail_provider)

    current = [
        {"year": "2026.08", "hsCode": "8542321010", "expDlr": "1200000000", "expWgt": "100000"},
        {"year": "2026.08", "hsCode": "8542321030", "expDlr": "500000000", "expWgt": "50000"},
        {"year": "2026.08", "hsCode": "8542321020", "expDlr": "100000000", "expWgt": "10000"},
        {"year": "2026.08", "hsCode": "854231", "expDlr": "700000000", "expWgt": "70000"},
        {"year": "2026.08", "hsCode": "854239", "expDlr": "300000000", "expWgt": "30000"},
    ]
    prior = [
        {"year": "2025.08", "hsCode": "8542321010", "expDlr": "1000000000", "expWgt": "100000"},
        {"year": "2025.08", "hsCode": "8542321030", "expDlr": "400000000", "expWgt": "50000"},
        {"year": "2025.08", "hsCode": "8542321020", "expDlr": "100000000", "expWgt": "10000"},
        {"year": "2025.08", "hsCode": "854231", "expDlr": "600000000", "expWgt": "70000"},
        {"year": "2025.08", "hsCode": "854239", "expDlr": "250000000", "expWgt": "30000"},
    ]
    rows = export_service._build_semiconductor_breakdown_from_rows(current, prior, "202608")
    dram = next(row for row in rows if row["key"] == "dram")
    flash = next(row for row in rows if row["key"] == "flash")
    assert dram["code"] == "8542321010"
    assert dram["exportYoY"] == 20.0
    assert dram["history"] == []
    assert flash["code"] == "8542321030"
    assert flash["exportYoY"] == 25.0


def test_semiconductor_breakdown_preserves_flash_as_broader_than_nand():
    flash = next(row for row in export_service.SEMICONDUCTOR_SEGMENTS if row["key"] == "flash")
    assert flash["code"] == "8542321030"
    assert flash["name"] == "Flash memory"
    assert "NAND" in flash["note"]


def test_country_total_row_wins_over_hs_detail():
    rows = [
        {"year": "총계", "hsCd": "-", "expDlr": "999"},
        {"year": "2026.09", "hsCd": "85", "expDlr": "100"},
        {"year": "2026.09", "hsCd": "87", "expDlr": "50"},
    ]
    assert export_service._country_export(rows, "202609") == 999


def test_item_period_falls_back_when_latest_month_has_no_hs_rows(monkeypatch):
    def fake_rows(period):
        if period == "202609":
            return []
        if period == "202608":
            return [{"year": "2026.08", "hsCode": "8542310000", "expDlr": "10"}]
        return []
    monkeypatch.setattr(export_service, "_fetch_item_rows", fake_rows)
    period, rows = export_service._find_item_period("202609")
    assert period == "202608"
    assert rows[0]["hsCode"] == "8542310000"


def test_snapshot_builds_real_history_contract_without_fake_checkpoints(monkeypatch):
    monthly = {}
    for year in (2025, 2026):
        for month in range(1, 10):
            key = f"{year}{month:02d}"
            base = 50_000_000_000 + month * 1_000_000_000
            if year == 2026:
                base *= 1.10
            monthly[key] = {
                "exports": base,
                "imports": base * 0.85,
                "balance": base * 0.15,
            }

    requested_end = {}
    def fake_total_history(end):
        requested_end["value"] = end
        return monthly
    monkeypatch.setattr(export_service, "_fetch_total_history", fake_total_history)

    items = [
        {
            "name": "반도체",
            "exportsUsdBillion": 20.0,
            "exportYoY": 25.0,
            "note": "HS 8541+8542 합산",
        }
    ]
    regions = [
        {
            "name": "미국",
            "exportsUsdBillion": 12.0,
            "exportYoY": 8.0,
            "note": "관세청 국가코드 US 기준",
        }
    ]

    monkeypatch.setattr(
        export_service,
        "_find_item_period",
        lambda latest: ("202608", [{"year": "2026.08", "hsCode": "8542310000", "expDlr": "1"}]),
    )
    monkeypatch.setattr(
        export_service,
        "_fetch_item_rows",
        lambda period: [{"year": "2025.08", "hsCode": "8542310000", "expDlr": "1"}],
    )
    monkeypatch.setattr(export_service, "_build_items_from_rows", lambda *args: items)
    monkeypatch.setattr(export_service, "_build_hs2_breadth", lambda *args: {
        "period": "2026-08", "level": "HS2", "comparableCount": 10,
        "risingCount": 6, "fallingCount": 4, "flatCount": 0,
        "risingBreadthPct": 60.0, "risingExportSharePct": 70.0,
        "netChangeUsdBillion": 1.2, "topPositive": [], "topNegative": [],
    })
    monkeypatch.setattr(export_service, "_find_region_period", lambda latest: "202608")
    monkeypatch.setattr(export_service, "_parallel_optional", lambda *args, **kwargs: (regions, []))

    snapshot = export_service._build_snapshot(datetime(2026, 10, 2, 12, 0))
    assert snapshot["status"] == "official_api"
    assert requested_end["value"] == "202609"
    assert snapshot["period"] == "2026-09"
    assert len(snapshot["history"]) == 12
    assert snapshot["history"][-1]["exportYoY"] == 10.0
    assert snapshot["checkpoints"] == []
    assert snapshot["itemPeriod"] == "2026-08"
    assert snapshot["regionPeriod"] == "2026-08"
    assert snapshot["items"][0]["name"] == "반도체"
    assert snapshot["breadth"]["risingBreadthPct"] == 60.0
    assert snapshot["regions"][0]["name"] == "미국"
    assert snapshot["summary"]["exportsUsdBillion"] > 0


def test_total_month_parser_ignores_total_row():
    rows = [
        {"year": "2026.09", "expDlr": "60000000000", "impDlr": "50000000000", "balPayments": "10000000000"},
        {"year": "총계", "expDlr": "999999999999", "impDlr": "1", "balPayments": "1"},
    ]
    parsed = export_service._total_months(rows)
    assert list(parsed) == ["202609"]
    assert parsed["202609"]["exports"] == 60_000_000_000
