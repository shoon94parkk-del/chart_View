"""Exercise the overlapping provider responses used by the existing MoM fetch."""
import copy

import pytest

import export_momentum_service as service


def row(code, amount, weight, *, month="2026.08", code_field="hsCode"):
    return {"year": month, code_field: code, "expDlr": str(amount), "expWgt": str(weight)}


def collect(monkeypatch, responses):
    def request(url, **params):
        assert url == service.ITEM_URL
        assert params["strtYymm"] == params["endYymm"] == "202608"
        result = responses.get(params["hsSgn"], [])
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)

    monkeypatch.setattr(service, "_request_rows", request)
    return service._fetch_semiconductor_previous_month_rows("202608")


@pytest.mark.parametrize(
    "key,code,previous,current,expected_mom",
    [
        ("dram", "8542321010", 15_733_100_000, 16_777_000_000, 6.6),
        ("flash", "8542321030", 100, 120, 20.0),
        ("mcp-memory", "8542323000", 200, 250, 25.0),
    ],
)
def test_overlapping_memory_and_exact_queries_do_not_double_mom_baseline(
    monkeypatch, key, code, previous, current, expected_mom
):
    # A 6-digit memory query also returns the 10-digit row requested separately.
    previous_row = row(code, previous, 100)
    collected = collect(monkeypatch, {"854232": [previous_row], code: [previous_row]})
    result = service._build_semiconductor_breakdown_from_rows(
        [row(code, current, 120, month="2026.09")], [], collected, "202609"
    )
    segment = next(item for item in result if item["key"] == key)
    assert segment["exportMoM"] == expected_mom
    assert segment["exportWeightMoM"] == 20.0
    # Duplicating both denominators used to cancel in this ratio; preserve it.
    expected_unit_mom = round(((current / 120) / (previous / 100) - 1) * 100, 1)
    assert segment["unitValueMoM"] == expected_unit_mom
    assert segment["exportYoY"] is None


def test_mom_dedup_preserves_parent_leaf_priority_and_independent_module(monkeypatch):
    dram = row("8542321010", 40, 4)
    flash = row("8542321030", 20, 2)
    mcp = row("8542323000", 30, 3)
    sram = row("8542321020", 10, 1)
    parent = row("854232", 150, 15)
    module = row("8473304060", 70, 7)
    collected = collect(monkeypatch, {
        "854232": [parent, dram, flash, mcp, sram],
        "8542321010": [dram], "8542321030": [flash],
        "8542323000": [mcp], "8473304060": [module],
    })
    assert service._hs_prefix_export(collected, "854232", "202608") == 150
    assert service._hs_prefix_weight(collected, "854232", "202608") == 15
    assert service._hs_prefix_export(collected, "8542321020", "202608") == 10
    assert service._hs_prefix_export(collected, "8473304060", "202608") == 70


def test_mom_dedup_normalizes_month_hs_alias_and_numeric_format(monkeypatch):
    collected = collect(monkeypatch, {
        "854232": [row("8542321010", "1,000", "100", month="2026.08")],
        "8542321010": [row("8542321010", "1000.0", "100.0", month="202608", code_field="hsCd")],
    })
    assert service._hs_prefix_export(collected, "8542321010", "202608") == 1000
    assert service._hs_prefix_weight(collected, "8542321010", "202608") == 100


@pytest.mark.parametrize("field", ["expDlr", "expWgt"])
def test_conflicting_mom_observations_omit_optional_comparison(monkeypatch, field):
    first = row("8542321010", 100_000_000, 10)
    conflict = {**first, field: "999000000"}
    collected = collect(monkeypatch, {"854232": [first], "8542321010": [conflict]})
    result = service._build_semiconductor_breakdown_from_rows(
        [row("8542321010", 120_000_000, 12, month="2026.09")], [], collected, "202609"
    )
    dram = next(item for item in result if item["key"] == "dram")
    assert dram["exportsUsdBillion"] == 0.12
    assert dram["exportMoM"] is None
    assert dram["exportWeightMoM"] is None
    assert dram["unitValueMoM"] is None


def test_mom_dedup_retains_available_weight_from_duplicate(monkeypatch):
    first = row("8542321010", 100, "")
    complete = row("8542321010", 100, 10)
    collected = collect(monkeypatch, {"854232": [first], "8542321010": [complete]})
    assert service._hs_prefix_export(collected, "8542321010", "202608") == 100
    assert service._hs_prefix_weight(collected, "8542321010", "202608") == 10


def test_mom_query_failure_preserves_other_available_segments(monkeypatch):
    collected = collect(monkeypatch, {
        "854232": [row("8542321010", 100, 10)],
        "8542321010": service.CustomsApiError("unavailable"),
        "8473304060": [row("8473304060", 70, 7)],
    })
    assert service._hs_prefix_export(collected, "8542321010", "202608") == 100
    assert service._hs_prefix_export(collected, "8473304060", "202608") == 70
