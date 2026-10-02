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


def test_hs_export_prefers_exact_requested_code():
    rows = [
        {"year": "2026.09", "hsCd": "85", "expDlr": "500"},
        {"year": "2026.09", "hsCd": "8541", "expDlr": "120"},
        {"year": "2026.09", "hsCd": "8542", "expDlr": "300"},
        {"year": "2026.09", "hsCd": "854231", "expDlr": "250"},
    ]
    assert export_service._hs_export(rows, "8542", "202609") == 300


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

    def fake_parallel(builder, rows, latest, prior, workers=6):
        if rows is export_service.ITEM_GROUPS:
            return items, []
        return regions, []

    monkeypatch.setattr(export_service, "_parallel_optional", fake_parallel)
    monkeypatch.setattr(export_service, "_fetch_hs_export", lambda code, period: 10_000_000_000)

    snapshot = export_service._build_snapshot(datetime(2026, 10, 2, 12, 0))
    assert snapshot["status"] == "official_api"
    assert requested_end["value"] == "202609"
    assert snapshot["period"] == "2026-09"
    assert len(snapshot["history"]) == 12
    assert snapshot["history"][-1]["exportYoY"] == 10.0
    assert snapshot["checkpoints"] == []
    assert snapshot["items"][0]["name"] == "반도체"
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
