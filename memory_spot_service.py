from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    import redis.asyncio as redis_async
except Exception:
    redis_async = None

router = APIRouter()

DRAM_SOURCE_URL = "https://www.trendforce.com/price/dram/module_spot"
NAND_SOURCE_URL = "https://www.trendforce.com/price/flash/wafer_contract"
CACHE_TTL_SEC = 60 * 60 * 6
FAILURE_RETRY_SEC = 60 * 15
HISTORY_LIMIT = 365
REDIS_KEY = "chartview:memory-spot:history:v2"

GROUP_SPECS = [
    {
        "key": "dram-chip",
        "name": "DRAM 칩 현물",
        "family": "DRAM",
        "sourceUrl": DRAM_SOURCE_URL,
        "items": [
            ("ddr5-16gb", "DDR5 16Gb (2Gx8) 4800/5600"),
            ("ddr4-16gb", "DDR4 16Gb (2Gx8) 3200"),
            ("ddr4-8gb", "DDR4 8Gb (1Gx8) 3200"),
        ],
    },
    {
        "key": "dram-module",
        "name": "DRAM 모듈 현물",
        "family": "DRAM",
        "sourceUrl": DRAM_SOURCE_URL,
        "items": [
            ("ddr5-udimm-16gb", "DDR5 UDIMM 16GB 4800/5600"),
            ("ddr5-rdimm-32gb", "DDR5 RDIMM 32GB 4800/5600"),
            ("ddr4-udimm-16gb", "DDR4 UDIMM 16GB 3200"),
        ],
    },
    {
        "key": "gddr",
        "name": "GDDR 현물",
        "family": "DRAM",
        "sourceUrl": DRAM_SOURCE_URL,
        "items": [
            ("gddr5-8gb", "GDDR5 8Gb"),
            ("gddr6-8gb", "GDDR6 8Gb"),
        ],
    },
    {
        "key": "nand-chip",
        "name": "NAND 칩 현물",
        "family": "NAND",
        "sourceUrl": NAND_SOURCE_URL,
        "items": [
            ("nand-slc-2gb", "SLC 2Gb 256MBx8"),
            ("nand-slc-1gb", "SLC 1Gb 128MBx8"),
            ("nand-mlc-64gb", "MLC 64Gb 8GBx8"),
            ("nand-mlc-32gb", "MLC 32Gb 4GBx8"),
        ],
    },
    {
        "key": "nand-wafer",
        "name": "NAND TLC 웨이퍼 현물",
        "family": "NAND",
        "sourceUrl": NAND_SOURCE_URL,
        "items": [
            ("nand-tlc-512gb", "512Gb TLC"),
            ("nand-tlc-256gb", "256Gb TLC"),
            ("nand-tlc-128gb", "128Gb TLC"),
        ],
    },
]

ITEM_META: dict[str, dict[str, Any]] = {}
LABEL_TO_KEY: dict[str, str] = {}
GROUP_BY_KEY = {group["key"]: group for group in GROUP_SPECS}
for group in GROUP_SPECS:
    for item_key, label in group["items"]:
        ITEM_META[item_key] = {
            "key": item_key,
            "name": label,
            "groupKey": group["key"],
            "groupName": group["name"],
            "family": group["family"],
            "sourceUrl": group["sourceUrl"],
        }
        LABEL_TO_KEY[label] = item_key

# Verified public snapshots only. They seed the chart until Chart View accumulates
# newer source dates. Paid TrendForce history is never backfilled.
BOOTSTRAP_HISTORY = [
    {
        "date": "2026-09-21",
        "provider": "TrendForce",
        "sourceUrls": [DRAM_SOURCE_URL, NAND_SOURCE_URL],
        "values": {
            "ddr5-udimm-16gb": 239.0,
            "ddr5-rdimm-32gb": 2100.0,
            "ddr4-udimm-16gb": 165.10,
            "gddr5-8gb": 11.818,
            "gddr6-8gb": 11.844,
            "nand-slc-2gb": 4.345,
            "nand-slc-1gb": 3.358,
            "nand-mlc-64gb": 40.75,
            "nand-mlc-32gb": 19.30,
            "nand-tlc-512gb": 19.883,
            "nand-tlc-256gb": 17.885,
            "nand-tlc-128gb": 9.967,
        },
    },
    {
        "date": "2026-10-02",
        "provider": "TrendForce",
        "sourceUrls": [DRAM_SOURCE_URL],
        "values": {
            "ddr5-16gb": 58.0,
            "ddr4-16gb": 83.588,
            "ddr4-8gb": 46.321,
        },
    },
]

_cache: dict[str, Any] = {"payload": None, "timestamp": 0.0}
_memory_history = list(BOOTSTRAP_HISTORY)
_redis_client = None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _source_stamp(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        r"Last\s+Update\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*\(GMT\+8\)",
        text,
        flags=re.I,
    )
    if not match:
        return None, None
    date, clock = match.groups()
    return date, f"{date}T{clock}:00+08:00"


def _nearest_source_stamp(tr) -> tuple[str | None, str | None]:
    table = tr.find_parent("table")
    if table is None:
        return None, None
    node = table
    scanned = 0
    while node is not None and scanned < 80:
        node = node.previous_element
        scanned += 1
        if not isinstance(node, str):
            continue
        text = node.strip()
        if "Last Update" not in text:
            continue
        date, updated_at = _source_stamp(text)
        if date:
            return date, updated_at
    return None, None


def _parse_public_page(html: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    rows_by_group: dict[str, list[dict[str, Any]]] = {}
    group_stamps: dict[str, tuple[str | None, str | None]] = {}

    for tr in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.select("th,td")]
        if len(cells) < 7:
            continue
        item_key = LABEL_TO_KEY.get(cells[0])
        if not item_key:
            continue
        meta = ITEM_META[item_key]
        if meta["sourceUrl"] != source_url:
            continue

        source_date, updated_at = _nearest_source_stamp(tr)
        group_key = meta["groupKey"]
        if group_key not in group_stamps or source_date:
            group_stamps[group_key] = (source_date, updated_at)

        rows_by_group.setdefault(group_key, []).append(
            {
                **meta,
                "dailyHigh": _number(cells[1]),
                "dailyLow": _number(cells[2]),
                "sessionHigh": _number(cells[3]),
                "sessionLow": _number(cells[4]),
                "average": _number(cells[5]),
                "changePct": _number(cells[6]),
                "unit": "USD",
            }
        )

    groups: list[dict[str, Any]] = []
    for spec in GROUP_SPECS:
        if spec["sourceUrl"] != source_url:
            continue
        rows = rows_by_group.get(spec["key"], [])
        expected_keys = [key for key, _ in spec["items"]]
        row_map = {row["key"]: row for row in rows}
        ordered = [row_map[key] for key in expected_keys if key in row_map]
        if not ordered:
            continue
        source_date, updated_at = group_stamps.get(spec["key"], (None, None))
        groups.append(
            {
                "key": spec["key"],
                "name": spec["name"],
                "family": spec["family"],
                "provider": "TrendForce",
                "sourceUrl": source_url,
                "sourceDate": source_date,
                "updatedAt": updated_at,
                "items": ordered,
            }
        )

    return {"provider": "TrendForce", "groups": groups}


def parse_trendforce_dram_spot(html: str) -> dict[str, Any]:
    """Backwards-compatible parser used by existing tests and callers."""
    parsed = _parse_public_page(html, DRAM_SOURCE_URL)
    group = next((item for item in parsed["groups"] if item["key"] == "dram-chip"), None)
    if not group or len(group["items"]) != 3:
        raise ValueError("TrendForce DRAM table parse incomplete")
    return {
        "provider": "TrendForce",
        "sourceUrl": DRAM_SOURCE_URL,
        "sourceDate": group.get("sourceDate"),
        "updatedAt": group.get("updatedAt"),
        "items": group["items"],
    }


def _fetch_source_sync(source_url: str) -> dict[str, Any]:
    response = requests.get(
        source_url,
        timeout=10,
        headers={
            "User-Agent": "ChartView/1.0 (+https://chart-view-pkv8.onrender.com; public-data cache)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    return _parse_public_page(response.text, source_url)


def _bootstrap_group(spec: dict[str, Any]) -> dict[str, Any] | None:
    rows = []
    source_date = None
    for snapshot in BOOTSTRAP_HISTORY:
        values = snapshot.get("values") or {}
        matched = [key for key, _ in spec["items"] if key in values]
        if not matched:
            continue
        source_date = snapshot["date"]
        rows = []
        for key, label in spec["items"]:
            if key not in values:
                continue
            meta = ITEM_META[key]
            rows.append(
                {
                    **meta,
                    "name": label,
                    "dailyHigh": None,
                    "dailyLow": None,
                    "sessionHigh": None,
                    "sessionLow": None,
                    "average": values[key],
                    "changePct": None,
                    "unit": "USD",
                }
            )
    if not rows:
        return None
    return {
        "key": spec["key"],
        "name": spec["name"],
        "family": spec["family"],
        "provider": "TrendForce",
        "sourceUrl": spec["sourceUrl"],
        "sourceDate": source_date,
        "updatedAt": None,
        "items": rows,
        "stale": True,
    }


def _merge_group_results(results: list[dict[str, Any]], errors: dict[str, str]) -> dict[str, Any]:
    available: dict[str, dict[str, Any]] = {}
    for result in results:
        for group in result.get("groups", []):
            if group.get("items"):
                available[group["key"]] = group

    groups = []
    for spec in GROUP_SPECS:
        group = available.get(spec["key"]) or _bootstrap_group(spec)
        if not group:
            continue
        group = dict(group)
        if spec["sourceUrl"] in errors:
            group["stale"] = True
            group["fetchError"] = errors[spec["sourceUrl"]]
        else:
            group["stale"] = bool(group.get("stale", False))
        groups.append(group)

    dram = next((group for group in groups if group["key"] == "dram-chip"), None)
    source_dates = sorted({group["sourceDate"] for group in groups if group.get("sourceDate")})
    return {
        "provider": "TrendForce",
        "groups": groups,
        "items": (dram or {}).get("items", []),
        "sourceUrl": (dram or {}).get("sourceUrl") or DRAM_SOURCE_URL,
        "sourceDate": (dram or {}).get("sourceDate") or (source_dates[-1] if source_dates else None),
        "updatedAt": (dram or {}).get("updatedAt"),
        "stale": any(group.get("stale") for group in groups),
        "unavailablePriceSeries": [
            {
                "key": "hbm",
                "name": "HBM",
                "reason": "공개 현물 가격표에서 독립 가격 수치를 제공하지 않음",
            },
            {
                "key": "mcp",
                "name": "MCP",
                "reason": "공개 현물 가격표에서 독립 MCP 가격 수치를 제공하지 않음",
            },
            {
                "key": "emmc-ufs",
                "name": "eMMC / UFS",
                "reason": "공개 페이지에 품목명은 있으나 현재 숫자형 현물/계약 가격이 공개되지 않음",
            },
        ],
    }


def _fetch_latest_sync() -> dict[str, Any]:
    results = []
    errors: dict[str, str] = {}
    for source_url in [DRAM_SOURCE_URL, NAND_SOURCE_URL]:
        try:
            results.append(_fetch_source_sync(source_url))
        except Exception as exc:
            errors[source_url] = type(exc).__name__
    if not results and not BOOTSTRAP_HISTORY:
        raise RuntimeError("all memory price sources failed")
    return _merge_group_results(results, errors)


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.environ.get("CHARTVIEW_DATA_REDIS") or os.environ.get("CHARTVIEW_ANALYTICS_REDIS") or ""
    if not url or redis_async is None:
        return None
    try:
        client = redis_async.from_url(url, decode_responses=True, socket_timeout=1.5)
        await client.ping()
        _redis_client = client
        return client
    except Exception:
        return None


def _merge_history(history: list[dict[str, Any]], latest: dict[str, Any] | None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in [*BOOTSTRAP_HISTORY, *(history or [])]:
        date = str(row.get("date") or "").strip()
        if date:
            previous = merged.get(date, {})
            values = {**(previous.get("values") or {}), **(row.get("values") or {})}
            merged[date] = {**previous, **row, "values": values}

    if latest:
        grouped: dict[str, dict[str, Any]] = {}
        groups = list(latest.get("groups", []))
        if not groups and latest.get("items"):
            groups = [{
                "sourceDate": latest.get("sourceDate"),
                "sourceUrl": latest.get("sourceUrl") or DRAM_SOURCE_URL,
                "items": latest.get("items", []),
            }]
        for group in groups:
            date = str(group.get("sourceDate") or "").strip()
            if not date:
                continue
            bucket = grouped.setdefault(
                date,
                {
                    "date": date,
                    "provider": latest.get("provider") or "TrendForce",
                    "sourceUrls": [],
                    "values": {},
                },
            )
            source_url = group.get("sourceUrl")
            if source_url and source_url not in bucket["sourceUrls"]:
                bucket["sourceUrls"].append(source_url)
            for row in group.get("items", []):
                if row.get("key") in ITEM_META and row.get("average") is not None:
                    bucket["values"][row["key"]] = row["average"]

        for date, row in grouped.items():
            previous = merged.get(date, {})
            merged[date] = {
                **previous,
                **row,
                "values": {**(previous.get("values") or {}), **row["values"]},
            }

    return [merged[key] for key in sorted(merged)][-HISTORY_LIMIT:]


async def _load_history(latest: dict[str, Any] | None) -> tuple[list[dict[str, Any]], str]:
    global _memory_history
    client = await _get_redis()
    if client is None:
        _memory_history = _merge_history(_memory_history, latest)
        return _memory_history, "memory"

    try:
        raw = await client.get(REDIS_KEY)
        stored = json.loads(raw) if raw else []
        history = _merge_history(stored if isinstance(stored, list) else [], latest)
        await client.set(REDIS_KEY, json.dumps(history, ensure_ascii=False), ex=60 * 60 * 24 * 400)
        return history, "render-key-value"
    except Exception:
        _memory_history = _merge_history(_memory_history, latest)
        return _memory_history, "memory"


async def _latest_payload() -> tuple[dict[str, Any], bool]:
    now = time.time()
    cached = _cache.get("payload")
    if cached and now - float(_cache.get("timestamp") or 0) < CACHE_TTL_SEC:
        return cached, True

    try:
        payload = await asyncio.to_thread(_fetch_latest_sync)
        _cache["payload"] = payload
        _cache["timestamp"] = now
        return payload, False
    except Exception as exc:
        retry_timestamp = now - CACHE_TTL_SEC + FAILURE_RETRY_SEC
        if cached:
            fallback = dict(cached)
            fallback["stale"] = True
            fallback["fetchError"] = type(exc).__name__
            _cache["payload"] = fallback
            _cache["timestamp"] = retry_timestamp
            return fallback, True
        fallback = _merge_group_results([], {DRAM_SOURCE_URL: type(exc).__name__, NAND_SOURCE_URL: type(exc).__name__})
        fallback["stale"] = True
        fallback["fetchError"] = type(exc).__name__
        _cache["payload"] = fallback
        _cache["timestamp"] = retry_timestamp
        return fallback, False


async def _memory_price_response():
    latest, cache_hit = await _latest_payload()
    history, history_storage = await _load_history(latest)
    body = {
        **latest,
        "history": history,
        "historyStorage": history_storage,
        "historyBasis": "Chart View accumulation of publicly visible latest prices; no paid historical backfill",
        "cacheHit": cache_hit,
        "schemaVersion": 2,
    }
    return JSONResponse(
        body,
        headers={
            "Cache-Control": "public, max-age=900, stale-while-revalidate=21600",
            "X-ChartView-Source": "trendforce-public-latest",
        },
    )


@router.get("/api/memory-prices")
async def memory_prices():
    return await _memory_price_response()


@router.get("/api/memory-spot")
async def memory_spot():
    return await _memory_price_response()
