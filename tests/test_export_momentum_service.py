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
        {"year": "2025.08", "hsCode": "8542323000", "expDlr": "800000000", "expWgt": "80000"},
        {"year": "2025.08", "hsCode": "8473304060", "expDlr": "300000000", "expWgt": "15000"},
        {"year": "2025.08", "hsCode": "854231", "expDlr": "600000000", "expWgt": "70000"},
        {"year": "2025.08", "hsCode": "854239", "expDlr": "250000000", "expWgt": "30000"},
    ]
    previous_month = [
        {"year": "2026.07", "hsCode": "8542321010", "expDlr": "1100000000", "expWgt": "95000"},
        {"year": "2026.07", "hsCode": "8542321030", "expDlr": "450000000", "expWgt": "48000"},
        {"year": "2026.07", "hsCode": "8542321020", "expDlr": "90000000", "expWgt": "9500"},
        {"year": "2026.07", "hsCode": "8542323000", "expDlr": "900000000", "expWgt": "70000"},
        {"year": "2026.07", "hsCode": "8473304060", "expDlr": "400000000", "expWgt": "18000"},
        {"year": "2026.07", "hsCode": "854231", "expDlr": "650000000", "expWgt": "68000"},
        {"year": "2026.07", "hsCode": "854239", "expDlr": "280000000", "expWgt": "29000"},
    ]
    current.extend([
        {"year": "2026.08", "hsCode": "8542323000", "expDlr": "1000000000", "expWgt": "75000"},
        {"year": "2026.08", "hsCode": "8473304060", "expDlr": "600000000", "expWgt": "20000"},
    ])
    rows = export_service._build_semiconductor_breakdown_from_rows(current, prior, previous_month, "202608")
    dram = next(row for row in rows if row["key"] == "dram")
    flash = next(row for row in rows if row["key"] == "flash")
    assert dram["code"] == "8542321010"
    assert dram["exportYoY"] == 20.0
    assert dram["exportMoM"] == pytest.approx(9.1)
    assert dram["unitValueMoM"] is not None
    assert dram["history"] == []
    assert flash["code"] == "8542321030"
    assert flash["exportYoY"] == 25.0
    assert flash["exportMoM"] == pytest.approx(11.1)
    mcp = next(row for row in rows if row["key"] == "mcp-memory")
    module = next(row for row in rows if row["key"] == "dram-module")
    assert mcp["code"] == "8542323000"
    assert module["code"] == "8473304060"
    assert module["exportMoM"] == 50.0


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


def test_item_period_falls_back_with_lightweight_probe_before_full_fetch(monkeypatch):
    probes = []
    full_fetches = []
    def fake_available(period):
        probes.append(period)
        return period == "202608"
    def fake_rows(period):
        full_fetches.append(period)
        return [{"year": "2026.08", "hsCode": "8542310000", "expDlr": "10"}]
    monkeypatch.setattr(export_service, "_item_period_available", fake_available)
    monkeypatch.setattr(export_service, "_fetch_item_rows", fake_rows)
    period, rows = export_service._find_item_period("202609")
    assert probes == ["202609", "202608"]
    assert full_fetches == ["202608"]
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
        "_find_item_period_candidate",
        lambda latest: "202608",
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



def test_semiconductor_mom_fetch_targets_only_five_report_codes(monkeypatch):
    calls = []
    def fake_request(url, **params):
        calls.append((url, params["hsSgn"], params["strtYymm"], params["endYymm"]))
        return [{
            "year": "2026.07",
            "hsCode": params["hsSgn"],
            "expDlr": "1000000",
            "expWgt": "100",
        }]
    monkeypatch.setattr(export_service, "_request_rows", fake_request)
    rows = export_service._fetch_semiconductor_previous_month_rows("202607")
    assert len(calls) == 5
    assert {code for _, code, _, _ in calls} == {
        "854232", "8542321010", "8542321030", "8542323000", "8473304060"
    }
    assert all(start == "202607" and end == "202607" for _, _, start, end in calls)
    assert len(rows) == 5


def test_semiconductor_report_official_codes_include_mcp_and_dram_module():
    mcp = next(row for row in export_service.SEMICONDUCTOR_SEGMENTS if row["key"] == "mcp-memory")
    module = next(row for row in export_service.SEMICONDUCTOR_SEGMENTS if row["key"] == "dram-module")
    assert mcp["code"] == "8542323000"
    assert "Multichip" in mcp["note"]
    assert module["code"] == "8473304060"
    assert "DRAM modules" in module["note"]



def test_item_period_candidate_uses_probe_without_full_table(monkeypatch):
    calls = []
    def fake_probe(period):
        calls.append(period)
        return period == "202607"
    monkeypatch.setattr(export_service, "_item_period_available", fake_probe)
    assert export_service._find_item_period_candidate("202609") == "202607"
    assert calls == ["202609", "202608", "202607"]



def test_semiconductor_country_pair_queries_exact_hsk_and_country(monkeypatch):
    calls = []
    def fake_request(url, **params):
        calls.append((url, params["strtYymm"], params["endYymm"], params["hsSgn"], params["cntyCd"]))
        value = "1200000000" if params["strtYymm"] == "202608" else "1000000000"
        return [{"year": params["strtYymm"][:4] + "." + params["strtYymm"][4:], "hsCd": params["hsSgn"], "expDlr": value}]
    monkeypatch.setattr(export_service, "_request_rows", fake_request)
    segment = next(row for row in export_service.SEMICONDUCTOR_SEGMENTS if row["key"] == "dram")
    country = {"name": "중국", "code": "CN"}
    row = export_service._fetch_semiconductor_country_pair(segment, country, "202608", "202508")
    assert calls == [
        (export_service.ITEM_COUNTRY_URL, "202608", "202608", "8542321010", "CN"),
        (export_service.ITEM_COUNTRY_URL, "202508", "202508", "8542321010", "CN"),
    ]
    assert row["exportsUsdBillion"] == pytest.approx(1.2)
    assert row["exportYoY"] == 20.0
    assert row["deltaUsdBillion"] == pytest.approx(0.2)


def test_semiconductor_country_matrix_is_configured_market_comparison(monkeypatch):
    values = {
        "CN": (4.0, 3.0),
        "HK": (2.0, 1.0),
        "VN": (1.5, 1.0),
        "TW": (1.0, 1.2),
        "US": (0.8, 0.7),
        "JP": (0.4, 0.5),
    }
    def fake_pair(segment, country, period, prior):
        current, previous = values[country["code"]]
        factor = {"dram": 1.0, "flash": 0.25, "mcp-memory": 0.7, "dram-module": 0.4}[segment["key"]]
        current *= factor
        previous *= factor
        return {
            "name": country["name"],
            "code": country["code"],
            "exportsUsdBillion": current,
            "priorExportsUsdBillion": previous,
            "exportYoY": export_service._pct(current, previous),
            "deltaUsdBillion": round(current - previous, 4),
        }
    monkeypatch.setattr(export_service, "_fetch_semiconductor_country_pair", fake_pair)
    snapshot = {
        "itemPeriod": "2026-08",
        "semiconductorBreakdown": [
            {"key": "dram", "exportsUsdBillion": 15.0},
            {"key": "flash", "exportsUsdBillion": 4.0},
            {"key": "mcp-memory", "exportsUsdBillion": 10.0},
            {"key": "dram-module", "exportsUsdBillion": 6.0},
        ],
    }
    matrix = export_service._build_semiconductor_country_matrix(snapshot)
    assert matrix["period"] == "2026-08"
    assert [row["code"] for row in matrix["markets"]] == ["CN", "HK", "VN", "TW", "US", "JP"]
    assert len(matrix["segments"]) == 4
    dram = next(row for row in matrix["segments"] if row["key"] == "dram")
    assert len(dram["countries"]) == 6
    assert dram["leaderCountry"] == "중국"
    assert dram["growthLeaderCountry"] == "중국"
    assert dram["declineLeaderCountry"] == "대만"
    china = next(row for row in dram["countries"] if row["code"] == "CN")
    assert china["sharePct"] == pytest.approx(26.7)
    assert "not a global ranking" in matrix["meta"]["scope"]



def test_ten_day_stage_parses_provider_period_labels_and_dates():
    assert export_service._ten_day_stage({"priodDt": "01~10"}) == 10
    assert export_service._ten_day_stage({"priodDt": "01~20"}) == 20
    assert export_service._ten_day_stage({"priodDt": "01~30"}) == 30
    assert export_service._ten_day_stage({"priodDt": "2026.09.10"}) == 10
    assert export_service._ten_day_stage({"priodDt": "2026.09.20"}) == 20
    assert export_service._ten_day_stage({"priodDt": "2026.09.30"}) == 30


def test_ten_day_amount_converts_thousand_dollars_to_billions():
    assert export_service._ten_day_amount_billion({"itemUsdAmt00": "34,973,000"}, "itemUsdAmt00") == pytest.approx(34.973)


def test_provisional_radar_builds_same_window_yoy_mom_acceleration_and_contribution(monkeypatch):
    rows = [
        {"priodMon": "2025.09", "priodDt": "01~10", "itemUsdAmt00": "20000000", "itemUsdAmt01": "5000000", "itemUsdAmt02": "1000000"},
        {"priodMon": "2025.09", "priodDt": "01~20", "itemUsdAmt00": "40000000", "itemUsdAmt01": "9000000", "itemUsdAmt02": "2000000"},
        {"priodMon": "2025.09", "priodDt": "01~30", "itemUsdAmt00": "60000000", "itemUsdAmt01": "12000000", "itemUsdAmt02": "3000000"},
        {"priodMon": "2026.08", "priodDt": "01~10", "itemUsdAmt00": "25000000", "itemUsdAmt01": "6000000", "itemUsdAmt02": "1100000"},
        {"priodMon": "2026.08", "priodDt": "01~20", "itemUsdAmt00": "50000000", "itemUsdAmt01": "12000000", "itemUsdAmt02": "2200000"},
        {"priodMon": "2026.08", "priodDt": "01~31", "itemUsdAmt00": "70000000", "itemUsdAmt01": "15000000", "itemUsdAmt02": "3300000"},
        {"priodMon": "2026.09", "priodDt": "01~10", "itemUsdAmt00": "30000000", "itemUsdAmt01": "10000000", "itemUsdAmt02": "1200000"},
        {"priodMon": "2026.09", "priodDt": "01~20", "itemUsdAmt00": "55000000", "itemUsdAmt01": "18000000", "itemUsdAmt02": "2500000"},
        {"priodMon": "2026.09", "priodDt": "01~30", "itemUsdAmt00": "80000000", "itemUsdAmt01": "24000000", "itemUsdAmt02": "3600000"},
    ]
    monkeypatch.setattr(export_service, "_fetch_ten_day_rows", lambda start, end: rows)
    radar = export_service._build_provisional_radar(datetime(2026, 10, 2, 18, 0))
    assert radar["period"] == "2026-09"
    assert radar["latestStage"] == 30
    assert len(radar["checkpoints"]) == 3
    first = radar["checkpoints"][0]
    second = radar["checkpoints"][1]
    final = radar["checkpoints"][2]
    assert first["semiconductor"]["exportsUsdBillion"] == pytest.approx(10.0)
    assert first["semiconductor"]["exportYoY"] == 100.0
    assert first["semiconductor"]["exportMoM"] == pytest.approx(66.7)
    assert first["semiconductorSharePct"] == pytest.approx(33.3)
    assert second["semiconductorYoYAccelerationPp"] == pytest.approx(0.0)
    assert final["semiconductorContributionPct"] == pytest.approx(60.0)
    assert radar["items"][0]["name"] == "반도체"
    assert radar["meta"]["classification"].startswith("Korea Customs")


def test_ten_day_month_map_keeps_latest_row_per_stage():
    rows = [
        {"priodMon": "2026.09", "priodDt": "01~10", "itemUsdAmt00": "1"},
        {"priodMon": "2026.09", "priodDt": "01~10", "itemUsdAmt00": "2"},
    ]
    mapped = export_service._ten_day_month_map(rows)
    assert mapped["202609"][10]["itemUsdAmt00"] == "2"



def _synthetic_landing_month_map(current_month="202610", current_stage=20, final_current=None):
    data = {}
    month = "202301"
    for index in range(44):
        full_total = 60.0 + index
        full_semi = 18.0 + index * 0.7
        ratio10 = [0.28, 0.31, 0.34, 0.37][index % 4]
        ratio20 = [0.60, 0.66, 0.72, 0.78][index % 4]
        data[month] = {
            10: {
                "priodMon": export_service._display_period(month),
                "priodDt": "01~10",
                "itemUsdAmt00": str(full_total * ratio10 * 1_000_000),
                "itemUsdAmt01": str(full_semi * ratio10 * 1_000_000),
            },
            20: {
                "priodMon": export_service._display_period(month),
                "priodDt": "01~20",
                "itemUsdAmt00": str(full_total * ratio20 * 1_000_000),
                "itemUsdAmt01": str(full_semi * ratio20 * 1_000_000),
            },
            30: {
                "priodMon": export_service._display_period(month),
                "priodDt": "01~30",
                "itemUsdAmt00": str(full_total * 1_000_000),
                "itemUsdAmt01": str(full_semi * 1_000_000),
            },
        }
        month = export_service._month_shift(month, 1)

    current = {
        current_stage: {
            "priodMon": export_service._display_period(current_month),
            "priodDt": "01~20" if current_stage == 20 else "01~10",
            "itemUsdAmt00": str(84.0 * 1_000_000),
            "itemUsdAmt01": str(42.0 * 1_000_000),
        }
    }
    if final_current is not None:
        current[30] = {
            "priodMon": export_service._display_period(current_month),
            "priodDt": "01~31",
            "itemUsdAmt00": str(final_current[0] * 1_000_000),
            "itemUsdAmt01": str(final_current[1] * 1_000_000),
        }
    data[current_month] = current
    return data


def test_landing_projection_uses_median_completion_and_iqr_with_backtest():
    month_map = _synthetic_landing_month_map()
    projection = export_service._build_landing_projection(month_map, "202610")
    assert projection["status"] == "open"
    assert projection["stage"] == 20
    total = projection["total"]
    semi = projection["semiconductor"]
    assert total["historySampleCount"] >= 40
    assert 60 <= total["medianCompletionPct"] <= 78
    assert total["rangeLowUsdBillion"] < total["estimateUsdBillion"] < total["rangeHighUsdBillion"]
    assert total["backtest"]["sampleCount"] > 0
    assert total["backtest"]["medianAbsErrorPct"] is not None
    assert 0 <= total["backtest"]["rangeHitPct"] <= 100
    assert semi["estimateUsdBillion"] > 42.0


def test_landing_projection_final_review_compares_stage_estimate_with_actual():
    month_map = _synthetic_landing_month_map(current_month="202609", current_stage=20, final_current=(120.0, 60.0))
    projection = export_service._build_landing_projection(month_map, "202609")
    assert projection["status"] == "final-review"
    assert projection["stage"] == 20
    assert projection["total"]["actualUsdBillion"] == pytest.approx(120.0)
    assert projection["semiconductor"]["actualUsdBillion"] == pytest.approx(60.0)
    assert projection["total"]["actualErrorPct"] is not None


def test_landing_projection_final_without_10_or_20_stage_shows_actual_only():
    month_map = {
        "202609": {
            30: {
                "priodMon": "2026.09",
                "priodDt": "01~30",
                "itemUsdAmt00": "120000000",
                "itemUsdAmt01": "60000000",
            }
        }
    }
    projection = export_service._build_landing_projection(month_map, "202609")
    assert projection["status"] == "final"
    assert projection["stage"] == 30
    assert projection["total"] is None


def test_momentum_signal_separates_acceleration_turnaround_slowing_and_weakness():
    assert export_service._momentum_signal(25.0, 15.0, 20.0, 4.0)["key"] == "acceleration"
    assert export_service._momentum_signal(8.0, -2.0, 3.0, 6.0)["key"] == "turnaround"
    assert export_service._momentum_signal(18.0, 28.0, 22.0, -3.0)["key"] == "slowing"
    assert export_service._momentum_signal(-4.0, 2.0, -1.0, -6.0)["key"] == "weak"
    assert export_service._momentum_signal(12.0, 10.0, 11.0, 1.0)["key"] == "steady"


def test_momentum_map_reuses_group_history_and_keeps_explicit_scope(monkeypatch):
    history = [
        {"period": "2026-04", "exportsUsdBillion": 4.0, "exportYoY": 4.0, "exportWeightYoY": 1.0, "unitValueYoY": 3.0},
        {"period": "2026-05", "exportsUsdBillion": 4.2, "exportYoY": 5.0, "exportWeightYoY": 2.0, "unitValueYoY": 3.0},
        {"period": "2026-06", "exportsUsdBillion": 4.4, "exportYoY": 6.0, "exportWeightYoY": 2.0, "unitValueYoY": 4.0},
        {"period": "2026-07", "exportsUsdBillion": 4.8, "exportYoY": 10.0, "exportWeightYoY": 4.0, "unitValueYoY": 6.0},
        {"period": "2026-08", "exportsUsdBillion": 5.1, "exportYoY": 14.0, "exportWeightYoY": 5.0, "unitValueYoY": 8.0},
        {"period": "2026-09", "exportsUsdBillion": 5.6, "exportYoY": 22.0, "exportWeightYoY": 7.0, "unitValueYoY": 10.0},
    ]
    calls = []

    def fake_history(group, period):
        calls.append((group["key"], period))
        return history

    monkeypatch.setattr(export_service, "_momentum_history_for_group", fake_history)
    result = export_service._build_momentum_map({"itemPeriod": "2026-09"})

    assert result["period"] == "2026-09"
    assert len(result["items"]) == len(export_service.ITEM_GROUPS)
    assert len(calls) == len(export_service.ITEM_GROUPS)
    assert result["items"][0]["signal"] == "acceleration"
    assert result["items"][0]["deltaYoYPp"] == 8.0
    assert result["items"][0]["avg3mYoY"] == pytest.approx(15.3)
    assert "six explicit HS proxy groups" in result["meta"]["scope"]
