"""Durable public-latest memory prices must never invent observations or roll back."""
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import memory_spot_service as service

try:
    import memory_price_publication as publication
except ModuleNotFoundError:
    publication = SimpleNamespace()

NOW = "2026-11-10T10:35:00Z"


def fetched(day="2026-11-10", average=60.0):
    groups = []
    for spec in service.GROUP_SPECS:
        groups.append({
            "key": spec["key"], "name": spec["name"], "family": spec["family"],
            "provider": "TrendForce", "sourceUrl": spec["sourceUrl"],
            "sourceDate": day, "updatedAt": day + "T18:10:00+08:00", "stale": False,
            "items": [{**service.ITEM_META[key], "average": average, "dailyHigh": average,
                       "dailyLow": average, "sessionHigh": average, "sessionLow": average,
                       "changePct": -0.25, "unit": "USD"} for key, _ in spec["items"]],
        })
    return service._merge_group_results([{"groups": groups}], {})


def document(day="2026-11-09", average=60.0):
    payload = fetched(day, average)
    payload.update({
        "schemaVersion": 2, "generatedAt": "2026-11-09T10:35:00Z", "collectedAt": "2026-11-09T10:35:00Z",
        "history": [{"date": day, "provider": "TrendForce", "sourceUrls": [service.DRAM_SOURCE_URL, service.NAND_SOURCE_URL],
                     "values": {key: average for key in service.ITEM_META}}],
    })
    return payload


def call(name, *args, **kwargs):
    function = getattr(publication, name, None)
    assert callable(function), f"{name} must be implemented"
    return function(*args, **kwargs)


def test_valid_publication_is_a_detached_copy_and_keeps_actual_zero():
    original = document(average=0)
    result = call("validate_publication", original)
    assert result["groups"][0]["items"][0]["average"] == 0
    assert result["history"][0]["values"]["ddr5-16gb"] == 0
    result["history"][0]["values"]["ddr5-16gb"] = 10
    assert original["history"][0]["values"]["ddr5-16gb"] == 0


@pytest.mark.parametrize("path,value", [
    (("schemaVersion",), True), (("schemaVersion",), 1), (("provider",), "Other"),
    (("generatedAt",), "2026-11-09T10:35:00+00:00"), (("collectedAt",), "2026-11-09T10:35:00.123Z"),
    (("collectedAt",), "2026-02-30T10:35:00Z"), (("generatedAt",), "2026-11-09"),
    (("groups", 0, "key"), "hbm"), (("groups", 0, "sourceDate"), "2026-02-30"),
    (("groups", 0, "sourceUrl"), "https://evil.example/price"),
    (("groups", 0, "updatedAt"), "2026-11-08T18:10:00+08:00"),
    (("groups", 0, "items", 0, "key"), "hbm"), (("groups", 0, "items", 0, "unit"), "CNY"),
    (("groups", 0, "items", 0, "groupKey"), "nand-chip"),
    (("groups", 0, "items", 0, "average"), True), (("groups", 0, "items", 0, "average"), "60"),
    (("groups", 0, "items", 0, "average"), -1), (("groups", 0, "items", 0, "average"), float("nan")),
    (("groups", 0, "items", 0, "dailyHigh"), float("inf")),
    (("groups", 0, "items", 0, "changePct"), False),
    (("history", 0, "date"), "2026-11-9"), (("history", 0, "provider"), "Other"),
    (("history", 0, "sourceUrls"), ["https://evil.example"]),
    (("history", 0, "values", "ddr5-16gb"), "60"),
    (("history", 0, "values", "ddr5-16gb"), None),
    (("history", 0, "values", "ddr5-16gb"), float("nan")),
    (("history", 0, "values", "ddr5-16gb"), -1),
])
def test_invalid_schema_prices_dates_units_and_sources_fail_closed(path, value):
    payload = document()
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValueError):
        call("validate_publication", payload)


@pytest.mark.parametrize("change", [
    lambda data: data["groups"].append(deepcopy(data["groups"][0])),
    lambda data: data["groups"][0]["items"].append(deepcopy(data["groups"][0]["items"][0])),
    lambda data: data["groups"][0]["items"].pop(),
    lambda data: data["history"].append(deepcopy(data["history"][0])),
    lambda data: data["history"][0]["values"].update({"hbm": 60}),
])
def test_duplicate_or_unknown_observations_are_rejected(change):
    payload = document()
    change(payload)
    with pytest.raises(ValueError):
        call("validate_publication", payload)


def test_same_source_date_replaces_values_without_adding_a_fake_collection_date():
    previous = document()
    snapshot = fetched("2026-11-09", average=61)
    original = deepcopy(previous)
    result = call("build_publication", previous, snapshot, collected_at=NOW)
    assert result["generatedAt"] == NOW == result["collectedAt"]
    assert result["groups"][0]["sourceDate"] == "2026-11-09"
    assert result["groups"][0]["updatedAt"] == "2026-11-09T18:10:00+08:00"
    assert [row["date"] for row in result["history"]].count("2026-11-09") == 1
    assert not any(row["date"] == "2026-11-10" for row in result["history"])
    assert result["history"][-1]["values"]["ddr5-16gb"] == 61
    assert previous == original


def test_partial_source_failure_preserves_previous_group_and_does_not_merge_bootstrap_as_new():
    previous = document()
    current = fetched(average=61)
    for index, group in enumerate(current["groups"]):
        if group["family"] == "NAND":
            replacement = service._bootstrap_group(service.GROUP_BY_KEY[group["key"]])
            replacement["fetchError"] = "ReadTimeout"
            current["groups"][index] = replacement
    result = call("build_publication", previous, current, collected_at=NOW)
    groups = {group["key"]: group for group in result["groups"]}
    assert groups["nand-chip"]["sourceDate"] == "2026-11-09"
    assert groups["nand-chip"]["items"][0]["average"] == 60
    assert groups["nand-chip"]["stale"] is True
    assert groups["dram-chip"]["sourceDate"] == "2026-11-10"
    assert "nand-slc-2gb" not in result["history"][-1]["values"]


def test_regressing_group_date_or_same_day_update_time_cannot_overwrite_current_prices():
    previous = document()
    for field, value in [("sourceDate", "2026-11-08"), ("updatedAt", "2026-11-09T14:40:00+08:00")]:
        current = fetched("2026-11-09", average=1)
        current["groups"][0][field] = value
        if field == "sourceDate":
            current["groups"][0]["updatedAt"] = value + "T18:10:00+08:00"
        result = call("build_publication", previous, current, collected_at=NOW)
        assert result["groups"][0]["sourceDate"] == "2026-11-09"
        assert result["groups"][0]["items"][0]["average"] == 60
        assert result["history"][-1]["values"]["ddr5-16gb"] == 60


def test_all_source_fallbacks_or_all_regressions_fail_instead_of_advancing_publication():
    previous = document()
    failed = service._merge_group_results([], {service.DRAM_SOURCE_URL: "ReadTimeout", service.NAND_SOURCE_URL: "ReadTimeout"})
    for current in [failed, fetched("2026-11-08")]:
        with pytest.raises(ValueError):
            call("build_publication", previous, current, collected_at=NOW)


def test_incomplete_or_malformed_group_keeps_previous_without_poisoning_successful_groups():
    current = fetched(average=61)
    current["groups"][0]["items"].pop()
    current["groups"][1]["items"][0]["average"] = float("nan")
    result = call("build_publication", document(), current, collected_at=NOW)
    assert result["groups"][0]["items"][0]["average"] == 60
    assert result["groups"][1]["items"][0]["average"] == 60
    assert result["groups"][2]["items"][0]["average"] == 61


def test_history_is_sorted_bounded_to_365_and_preserves_all_known_values_on_same_day():
    previous = document()
    start = date(2025, 11, 10)
    previous["history"] = [
        {"date": (start + timedelta(days=index)).isoformat(), "provider": "TrendForce", "sourceUrls": [service.DRAM_SOURCE_URL],
         "values": {"ddr5-16gb": 10.0}} for index in range(364)
    ] + document()["history"]
    result = call("build_publication", previous, fetched(), collected_at=NOW)
    assert len(result["history"]) == 365
    assert result["history"][0]["date"] == "2025-11-11"
    assert result["history"][-1]["date"] == "2026-11-10"
    assert result["history"][-2]["values"]["nand-slc-2gb"] == 60
    assert result["items"] == result["groups"][0]["items"]
    assert call("validate_publication", result) == result


def test_source_url_union_is_preserved_when_groups_with_different_sources_share_a_date():
    previous = document()
    result = call("build_publication", previous, fetched("2026-11-09"), collected_at=NOW)
    assert set(result["history"][-1]["sourceUrls"]) == {service.DRAM_SOURCE_URL, service.NAND_SOURCE_URL}


def test_other_group_newer_date_cannot_authorize_a_later_observation_for_an_older_group():
    payload = document()
    payload.update({"generatedAt": NOW, "collectedAt": NOW})
    for group in payload["groups"]:
        if group["family"] == "NAND":
            group["sourceDate"] = "2026-11-10"
            group["updatedAt"] = "2026-11-10T18:10:00+08:00"
    payload["history"].append({
        "date": "2026-11-10", "provider": "TrendForce",
        "sourceUrls": [service.DRAM_SOURCE_URL, service.NAND_SOURCE_URL],
        "values": {**{key: 60 for key, meta in service.ITEM_META.items() if meta["family"] == "NAND"}, "ddr5-16gb": 60},
    })
    with pytest.raises(ValueError, match="group source date"):
        call("validate_publication", payload)
