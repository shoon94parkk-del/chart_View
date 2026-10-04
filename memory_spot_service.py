from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
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

SOURCE_URL = "https://www.trendforce.com/price/dram/module_spot"
CACHE_TTL_SEC = 60 * 60 * 6
HISTORY_LIMIT = 365
REDIS_KEY = "chartview:memory-spot:history:v1"

TARGET_ITEMS = {
    "ddr5-16gb": "DDR5 16Gb (2Gx8) 4800/5600",
    "ddr4-16gb": "DDR4 16Gb (2Gx8) 3200",
    "ddr4-8gb": "DDR4 8Gb (1Gx8) 3200",
}

# Publicly visible TrendForce prints used only as a tiny bootstrap so the chart
# is meaningful on day one. Ongoing history is accumulated by Chart View from
# the public latest-price page; paid historical datasets are not backfilled.
BOOTSTRAP_HISTORY = [
    {
        "date": "2026-10-02",
        "provider": "TrendForce",
        "sourceUrl": SOURCE_URL,
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


def _source_date(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        r"Last\s+Update\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*\(GMT\+8\)",
        text,
        flags=re.I,
    )
    if not match:
        return None, None
    date, clock = match.groups()
    return date, f"{date}T{clock}:00+08:00"


def parse_trendforce_dram_spot(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    source_date, updated_at = _source_date(soup.get_text(" ", strip=True))
    rows: list[dict[str, Any]] = []

    by_name = {label: key for key, label in TARGET_ITEMS.items()}
    for tr in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.select("th,td")]
        if len(cells) < 7:
            continue
        label = cells[0]
        key = by_name.get(label)
        if not key:
            continue
        rows.append(
            {
                "key": key,
                "name": label,
                "dailyHigh": _number(cells[1]),
                "dailyLow": _number(cells[2]),
                "sessionHigh": _number(cells[3]),
                "sessionLow": _number(cells[4]),
                "average": _number(cells[5]),
                "changePct": _number(cells[6]),
                "unit": "USD",
            }
        )

    if len(rows) != len(TARGET_ITEMS):
        raise ValueError(f"TrendForce DRAM table parse incomplete: {len(rows)}/{len(TARGET_ITEMS)}")

    return {
        "provider": "TrendForce",
        "sourceUrl": SOURCE_URL,
        "sourceDate": source_date,
        "updatedAt": updated_at,
        "items": rows,
    }


def _fetch_latest_sync() -> dict[str, Any]:
    response = requests.get(
        SOURCE_URL,
        timeout=10,
        headers={
            "User-Agent": "ChartView/1.0 (+https://chart-view-pkv8.onrender.com; public-data cache)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    return parse_trendforce_dram_spot(response.text)


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
            merged[date] = row

    if latest:
        date = latest.get("sourceDate")
        values = {
            row["key"]: row.get("average")
            for row in latest.get("items", [])
            if row.get("key") in TARGET_ITEMS and row.get("average") is not None
        }
        if date and values:
            merged[date] = {
                "date": date,
                "provider": latest.get("provider") or "TrendForce",
                "sourceUrl": latest.get("sourceUrl") or SOURCE_URL,
                "values": values,
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


def _fallback_latest() -> dict[str, Any]:
    last = BOOTSTRAP_HISTORY[-1]
    rows = []
    for key, label in TARGET_ITEMS.items():
        rows.append(
            {
                "key": key,
                "name": label,
                "dailyHigh": None,
                "dailyLow": None,
                "sessionHigh": None,
                "sessionLow": None,
                "average": last["values"].get(key),
                "changePct": None,
                "unit": "USD",
            }
        )
    return {
        "provider": "TrendForce",
        "sourceUrl": last["sourceUrl"],
        "sourceDate": last["date"],
        "updatedAt": None,
        "items": rows,
        "stale": True,
    }


async def _latest_payload() -> tuple[dict[str, Any], bool]:
    now = time.time()
    cached = _cache.get("payload")
    if cached and now - float(_cache.get("timestamp") or 0) < CACHE_TTL_SEC:
        return cached, True

    try:
        payload = await asyncio.to_thread(_fetch_latest_sync)
        payload["stale"] = False
        _cache["payload"] = payload
        _cache["timestamp"] = now
        return payload, False
    except Exception as exc:
        if cached:
            fallback = dict(cached)
            fallback["stale"] = True
            fallback["fetchError"] = type(exc).__name__
            return fallback, True
        fallback = _fallback_latest()
        fallback["fetchError"] = type(exc).__name__
        return fallback, False


@router.get("/api/memory-spot")
async def memory_spot():
    latest, cache_hit = await _latest_payload()
    history, history_storage = await _load_history(latest)
    body = {
        **latest,
        "history": history,
        "historyStorage": history_storage,
        "historyBasis": "Chart View daily collection from publicly visible latest prices; no paid historical backfill",
        "cacheHit": cache_hit,
    }
    return JSONResponse(
        body,
        headers={
            "Cache-Control": "public, max-age=900, stale-while-revalidate=21600",
            "X-ChartView-Source": "trendforce-public-latest",
        },
    )
