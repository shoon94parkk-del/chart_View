"""Validate and merge durable observations of TrendForce's public latest prices.

Collection timestamps describe the job; only provider dates key price history.
This module performs no I/O and never reconstructs paid historical prices.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import math
import re
from typing import Any

from memory_spot_service import (
    BOOTSTRAP_HISTORY, DRAM_SOURCE_URL, NAND_SOURCE_URL, GROUP_SPECS, GROUP_BY_KEY,
    HISTORY_LIMIT, ITEM_META, _merge_group_results, _merge_history,
)

HISTORY_BASIS = "Chart View accumulation of publicly visible latest prices; no paid historical backfill"
SOURCE_URLS = {DRAM_SOURCE_URL, NAND_SOURCE_URL}
_PRICE_FIELDS = ("dailyHigh", "dailyLow", "sessionHigh", "sessionLow")
_UNAVAILABLE = _merge_group_results([], {})["unavailablePriceSeries"]


def _day(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid memory source date")
    try:
        if date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError("invalid memory calendar date")


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("memory collection time must be canonical UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid memory collection time") from exc


def _number(value: Any, *, optional: bool = False, signed: bool = False):
    if optional and value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or (not signed and value < 0):
        raise ValueError("memory prices must be finite numeric nonnegative scalars")
    return value


def _group(data: Any) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("key"), str) or data["key"] not in GROUP_BY_KEY:
        raise ValueError("unknown memory price group")
    spec = GROUP_BY_KEY[data["key"]]
    for field in ("name", "family", "sourceUrl"):
        if data.get(field) != spec[field]:
            raise ValueError("memory group catalog metadata mismatch")
    if data.get("provider") != "TrendForce" or type(data.get("stale", False)) is not bool:
        raise ValueError("invalid memory group provenance")
    source_date = _day(data.get("sourceDate"))
    updated = data.get("updatedAt")
    if updated is not None:
        if not isinstance(updated, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00", updated):
            raise ValueError("invalid provider update time")
        try:
            stamp = datetime.fromisoformat(updated)
        except ValueError as exc:
            raise ValueError("invalid provider update time") from exc
        if stamp.date().isoformat() != source_date:
            raise ValueError("provider date and update time disagree")
    elif not data.get("stale", False):
        raise ValueError("fresh memory group has no provider update time")

    items = data.get("items")
    expected = [key for key, _ in spec["items"]]
    if not isinstance(items, list) or len(items) != len(expected):
        raise ValueError("incomplete memory price group")
    rows = {}
    for row in items:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str) or row["key"] not in expected or row["key"] in rows:
            raise ValueError("unknown or duplicate memory price item")
        meta = ITEM_META[row["key"]]
        if any(row.get(field) != value for field, value in meta.items()) or row.get("unit") != "USD":
            raise ValueError("memory item catalog or unit mismatch")
        rows[row["key"]] = {
            **meta, "unit": "USD", "average": _number(row.get("average")),
            **{field: _number(row.get(field), optional=True) for field in _PRICE_FIELDS},
            "changePct": _number(row.get("changePct"), optional=True, signed=True),
        }
    group = {
        "key": spec["key"], "name": spec["name"], "family": spec["family"], "provider": "TrendForce",
        "sourceUrl": spec["sourceUrl"], "sourceDate": source_date, "updatedAt": updated,
        "stale": data.get("stale", False), "items": [rows[key] for key in expected],
    }
    if "fetchError" in data:
        error = data["fetchError"]
        if not isinstance(error, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error) or not group["stale"]:
            raise ValueError("invalid memory source failure marker")
        group["fetchError"] = error
    return group


def _history(data: Any) -> list[dict]:
    if not isinstance(data, list) or not 1 <= len(data) <= HISTORY_LIMIT:
        raise ValueError("invalid memory history length")
    result, seen = [], set()
    for row in data:
        if not isinstance(row, dict):
            raise ValueError("invalid memory history row")
        day = _day(row.get("date"))
        if day in seen or (result and day < result[-1]["date"]):
            raise ValueError("memory history must have distinct sorted dates")
        seen.add(day)
        urls = row.get("sourceUrls")
        if not isinstance(urls, list) or not urls or any(not isinstance(url, str) or url not in SOURCE_URLS for url in urls) or len(set(urls)) != len(urls):
            raise ValueError("invalid memory history source URLs")
        values = row.get("values")
        if row.get("provider") != "TrendForce" or not isinstance(values, dict) or not values or any(key not in ITEM_META for key in values):
            raise ValueError("invalid memory history provider or product")
        result.append({"date": day, "provider": "TrendForce", "sourceUrls": list(urls),
                       "values": {key: _number(value) for key, value in values.items()}})
    return result


def validate_publication(data: Any) -> dict:
    """Return a detached API-v2 publication, or raise ValueError on invalid data."""
    if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 2 or data.get("provider") != "TrendForce":
        raise ValueError("invalid memory publication schema")
    generated, collected = _utc(data.get("generatedAt")), _utc(data.get("collectedAt"))
    if generated < collected:
        raise ValueError("memory publication predates collection")
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or len(raw_groups) != len(GROUP_SPECS):
        raise ValueError("memory publication requires all catalog groups")
    groups = [_group(group) for group in raw_groups]
    if len({group["key"] for group in groups}) != len(GROUP_SPECS):
        raise ValueError("duplicate memory publication group")
    latest_source_day = max(group["sourceDate"] for group in groups)
    if latest_source_day > collected.astimezone(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError("memory source date is after collection")
    history = _history(data.get("history"))
    if history[-1]["date"] > latest_source_day:
        raise ValueError("memory history is newer than its source groups")
    group_dates = {group["key"]: group["sourceDate"] for group in groups}
    for observation in history:
        if any(observation["date"] > group_dates[ITEM_META[key]["groupKey"]] for key in observation["values"]):
            raise ValueError("memory observation is newer than its group source date")
    history_by_day = {row["date"]: row["values"] for row in history}
    for group in groups:
        if group["sourceDate"] >= history[0]["date"]:
            values = history_by_day.get(group["sourceDate"], {})
            if any(values.get(row["key"]) != row["average"] for row in group["items"]):
                raise ValueError("current memory prices disagree with observed history")
    canonical = _merge_group_results([{"groups": groups}], {})
    for field in ("items", "sourceUrl", "sourceDate", "updatedAt", "stale"):
        if field in data and data[field] != canonical[field]:
            raise ValueError("memory legacy alias disagrees with catalog")
    if "unavailablePriceSeries" in data and data["unavailablePriceSeries"] != _UNAVAILABLE:
        raise ValueError("unknown unavailable memory series")
    return deepcopy({**canonical, "schemaVersion": 2, "generatedAt": data["generatedAt"],
                     "collectedAt": data["collectedAt"], "history": history, "historyBasis": HISTORY_BASIS})


def build_publication(previous: dict | None, fetched: dict, *, collected_at: str) -> dict:
    """Merge only validated fresh groups; preserve last good values on failure/regression."""
    now = _utc(collected_at)
    prior = validate_publication(previous) if previous is not None else None
    if prior and now < _utc(prior["generatedAt"]):
        raise ValueError("memory collection time regressed")
    if not isinstance(fetched, dict) or not isinstance(fetched.get("groups"), list):
        raise ValueError("invalid fetched memory prices")
    old_groups = {group["key"]: group for group in (prior or {}).get("groups", [])}
    candidates = {}
    for candidate in fetched["groups"]:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("key"), str) or candidate["key"] in candidates:
            raise ValueError("duplicate or invalid fetched memory group")
        candidates[candidate["key"]] = candidate
    selected, accepted = [], []
    for spec in GROUP_SPECS:
        old, candidate, error = old_groups.get(spec["key"]), candidates.get(spec["key"]), "source_unavailable"
        try:
            if not candidate or candidate.get("stale") or candidate.get("fetchError"):
                raise ValueError("source failed or returned bootstrap")
            group = _group(candidate)
            if group["sourceDate"] > now.astimezone(timezone(timedelta(hours=8))).date().isoformat():
                raise ValueError("future source date")
            if old and (group["sourceDate"] < old["sourceDate"] or (
                group["sourceDate"] == old["sourceDate"] and old.get("updatedAt") and group["updatedAt"] < old["updatedAt"]
            )):
                error = "source_date_regression"
                raise ValueError("provider date regressed")
            selected.append(group)
            accepted.append(group)
        except ValueError:
            if old:
                selected.append({**deepcopy(old), "stale": True, "fetchError": error})
    if not accepted:
        raise ValueError("all memory price sources failed or regressed")
    payload = _merge_group_results([{"groups": selected}], {})
    previous_history = (prior or {}).get("history", [])
    history = _merge_history(previous_history, {"provider": "TrendForce", "groups": accepted})
    # The existing merge helper replaces row metadata; retain the union of real
    # source URLs when independently dated groups share one observation date.
    urls_by_day = {}
    for row in [*BOOTSTRAP_HISTORY, *previous_history]:
        urls_by_day.setdefault(row["date"], set()).update(row.get("sourceUrls", []))
    for group in accepted:
        urls_by_day.setdefault(group["sourceDate"], set()).add(group["sourceUrl"])
    for row in history:
        row["sourceUrls"] = sorted(urls_by_day[row["date"]])
    return validate_publication({**payload, "schemaVersion": 2, "generatedAt": collected_at,
                                 "collectedAt": collected_at, "history": history})
