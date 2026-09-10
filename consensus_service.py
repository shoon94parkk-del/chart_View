"""Analyst consensus data for the valuation tab.

Yahoo's earningsTrend module exposes genuine EPS estimate snapshots for
current/7/30/60/90 days ago, plus current earnings/revenue estimate ranges and
revision counts. Revenue-estimate history is not backfilled by Yahoo, so this
project accumulates daily snapshots in static/data/consensus_history.json.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
CACHE_TTL = 900
DISK_MAX_AGE = 36 * 3600

_mem_lock = threading.Lock()
_mem_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_disk_lock = threading.Lock()
_disk_cache: dict[str, Any] | None = None
_history_cache: dict[str, Any] | None = None
_auth_lock = threading.Lock()
_auth_session: requests.Session | None = None
_auth_crumb: str | None = None
_auth_timestamp = 0.0


def _number(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("raw")
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("fmt") or value.get("raw")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_period(row: dict[str, Any]) -> dict[str, Any]:
    earnings = row.get("earningsEstimate") or {}
    revenue = row.get("revenueEstimate") or {}
    trend = row.get("epsTrend") or {}
    revisions = row.get("epsRevisions") or {}
    return {
        "period": row.get("period"),
        "endDate": _text(row.get("endDate")),
        "earnings": {
            "avg": _number(earnings.get("avg")),
            "low": _number(earnings.get("low")),
            "high": _number(earnings.get("high")),
            "analysts": _number(earnings.get("numberOfAnalysts")),
            "growth": _number(earnings.get("growth")),
            "yearAgoEps": _number(earnings.get("yearAgoEps")),
        },
        "epsTrend": {
            "current": _number(trend.get("current")),
            "7daysAgo": _number(trend.get("7daysAgo")),
            "30daysAgo": _number(trend.get("30daysAgo")),
            "60daysAgo": _number(trend.get("60daysAgo")),
            "90daysAgo": _number(trend.get("90daysAgo")),
        },
        "revisions": {
            "up7": _number(revisions.get("upLast7days")),
            "up30": _number(revisions.get("upLast30days")),
            "down7": _number(revisions.get("downLast7days")),
            "down30": _number(revisions.get("downLast30days")),
        },
        "revenue": {
            "avg": _number(revenue.get("avg")),
            "low": _number(revenue.get("low")),
            "high": _number(revenue.get("high")),
            "analysts": _number(revenue.get("numberOfAnalysts")),
            "growth": _number(revenue.get("growth")),
            "yearAgoRevenue": _number(revenue.get("yearAgoRevenue")),
        },
    }


def _parse_root(symbol: str, root: dict[str, Any]) -> dict[str, Any]:
    price = root.get("price") or {}
    rows: dict[str, dict[str, Any]] = {}
    for raw_row in (root.get("earningsTrend") or {}).get("trend") or []:
        period = raw_row.get("period")
        if period in ("0q", "+1q", "0y", "+1y"):
            rows[period] = _parse_period(raw_row)
    if not rows:
        raise ValueError(f"Yahoo returned no analyst consensus for {symbol}")
    return {
        "ticker": symbol,
        "name": _text(price.get("shortName")) or _text(price.get("longName")) or symbol,
        "currency": _text(price.get("currency")),
        "periods": rows,
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance earningsTrend",
    }


def _ensure_auth(force: bool = False) -> tuple[requests.Session, str]:
    global _auth_session, _auth_crumb, _auth_timestamp
    now = time.time()
    with _auth_lock:
        if not force and _auth_session is not None and _auth_crumb and now - _auth_timestamp < 1800:
            return _auth_session, _auth_crumb
        session = requests.Session()
        session.headers.update(HEADERS)
        try:
            session.get("https://fc.yahoo.com", timeout=7, allow_redirects=True)
        except Exception:
            pass
        crumb_res = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=8)
        crumb_res.raise_for_status()
        crumb = crumb_res.text.strip()
        if not crumb or "<" in crumb:
            raise ValueError("Yahoo crumb unavailable")
        _auth_session, _auth_crumb, _auth_timestamp = session, crumb, now
        return session, crumb


def fetch_live_consensus(symbol: str) -> dict[str, Any]:
    """Fetch a fresh analyst-consensus snapshot directly from Yahoo."""
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("empty symbol")
    session, crumb = _ensure_auth()
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
    params = {"modules": "price,earningsTrend", "crumb": crumb}
    for attempt in range(2):
        response = session.get(url, params=params, timeout=12)
        if response.status_code in (401, 403) and attempt == 0:
            session, crumb = _ensure_auth(force=True)
            params["crumb"] = crumb
            continue
        response.raise_for_status()
        root = (response.json().get("quoteSummary", {}).get("result") or [None])[0]
        if not root:
            raise ValueError(f"Yahoo quoteSummary returned no result for {symbol}")
        return _parse_root(symbol, root)
    raise ValueError(f"Yahoo consensus unavailable for {symbol}")


def _read_json(filename: str) -> dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "static", "data", filename)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _disk_payload() -> dict[str, Any]:
    global _disk_cache
    if _disk_cache is None:
        with _disk_lock:
            if _disk_cache is None:
                _disk_cache = _read_json("consensus_cache.json")
    return _disk_cache or {}


def _history_payload() -> dict[str, Any]:
    global _history_cache
    if _history_cache is None:
        with _disk_lock:
            if _history_cache is None:
                _history_cache = _read_json("consensus_history.json")
    return _history_cache or {}


def _cache_age_seconds(payload: dict[str, Any]) -> float | None:
    stamp = payload.get("generatedAt")
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _attach_history(snapshot: dict[str, Any], symbol: str) -> dict[str, Any]:
    out = json.loads(json.dumps(snapshot))
    hist = (_history_payload().get("history") or {}).get(symbol, {})
    out["history"] = hist if isinstance(hist, dict) else {}
    return out


def fetch_consensus(symbol: str) -> dict[str, Any]:
    """Return stable daily cache first; use live Yahoo for uncached tickers."""
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("empty symbol")
    now = time.time()
    with _mem_lock:
        cached = _mem_cache.get(symbol)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

    disk = _disk_payload()
    disk_row = (disk.get("quotes") or {}).get(symbol)
    age = _cache_age_seconds(disk)
    if isinstance(disk_row, dict) and (age is None or age <= DISK_MAX_AGE):
        result = _attach_history(disk_row, symbol)
        result["cacheMode"] = "daily"
        result["source"] = "Yahoo Finance earningsTrend · daily GitHub cache"
    else:
        result = _attach_history(fetch_live_consensus(symbol), symbol)
        result["cacheMode"] = "live"

    with _mem_lock:
        _mem_cache[symbol] = (now, result)
    return result
