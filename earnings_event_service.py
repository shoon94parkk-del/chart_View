"""Optional, precomputed official earnings-call schedules.

Conference-call times are not results-publication times. No provider I/O, EPS
comparison, inferred announcement date, or price-return calculation occurs here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "earnings-events-v1"
CACHE_PATH = Path(__file__).resolve().parent / "static/data/earnings_event_cache.json"
MAX_CHECK_AGE = timedelta(days=7)
ISSUERS = {
    "AAPL": {"name": "Apple", "sourceName": "Apple Investor Relations", "url": "https://investor.apple.com/investor-relations/default.aspx", "host": "investor.apple.com"},
    "NVDA": {"name": "NVIDIA", "sourceName": "NVIDIA Investor Relations", "url": "https://investor.nvidia.com/events-and-presentations/events-and-presentations/default.aspx", "host": "investor.nvidia.com"},
    "005930.KS": {"name": "삼성전자", "sourceName": "Samsung Electronics Investor Relations", "url": "https://www.samsung.com/global/ir/ir-events-presentations/events/", "host": "www.samsung.com"},
    "000660.KS": {"name": "SK하이닉스", "sourceName": None, "url": None, "host": None},
}


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("explicit timestamp required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timezone required")
    return stamp.astimezone(timezone.utc)


def _official_url(value: Any, host: str | None) -> bool:
    if not isinstance(value, str) or not host:
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and parsed.hostname == host and not parsed.username and not parsed.password and parsed.port in (None, 443)


def validate_event(value: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Fail closed on unsupported timing/provenance; derive display times once."""
    if not isinstance(value, dict):
        raise ValueError("event object required")
    symbol = value.get("symbol")
    issuer = ISSUERS.get(symbol)
    if not issuer or not issuer["host"]:
        raise ValueError("issuer not covered")
    if value.get("eventType") != "earnings_call" or value.get("timingRole") != "conference_call" or value.get("publishedAt") is not None:
        raise ValueError("only separately identified conference-call schedules supported")
    scheduled = parse_timestamp(value.get("scheduledAt"))
    zone = ZoneInfo(value.get("timezone"))
    source = value.get("source")
    if not isinstance(source, dict) or not all(_official_url(source.get(key), issuer["host"]) for key in ("url", "evidenceUrl")):
        raise ValueError("official source required")
    checked = parse_timestamp(source.get("checkedAt"))
    if now is not None and checked > now + timedelta(minutes=5):
        raise ValueError("future observation not verified")
    if source.get("publishedAt") is not None:
        if parse_timestamp(source["publishedAt"]) > checked:
            raise ValueError("source publication follows observation")
    if not re.fullmatch(r"[a-f0-9]{64}", str(source.get("contentSha256", ""))):
        raise ValueError("source content fingerprint required")
    if not all(isinstance(value.get(key), str) and value[key].strip() for key in ("id", "name", "title")):
        raise ValueError("event identity required")
    local = scheduled.astimezone(zone)
    # Whitelist fields so unchecked EPS, release-time or reaction data cannot leak.
    row = {key: value[key] for key in ("id", "symbol", "name", "title", "eventType", "timingRole", "timezone")}
    row.update({
        "scheduledAt": scheduled.isoformat().replace("+00:00", "Z"),
        "scheduledAtKst": scheduled.astimezone(ZoneInfo("Asia/Seoul")).isoformat(),
        "localDate": local.date().isoformat(), "localTime": local.strftime("%H:%M"),
        "publishedAt": None, "session": "unknown", "status": "confirmed_call",
        "source": {key: source.get(key) for key in ("name", "url", "evidenceUrl", "publishedAt", "checkedAt", "contentSha256")},
    })
    return row


def get_earnings_events(symbol: str | None = None, *, now: datetime | None = None, cache_path: Path | None = None) -> dict[str, Any]:
    """Read only the shipped cache. Old checks/past calls never become next calls."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        cache = json.loads((cache_path or CACHE_PATH).read_text(encoding="utf-8"))
        if not isinstance(cache, dict) or cache.get("schemaVersion") != SCHEMA_VERSION:
            cache = {}
    except (OSError, ValueError):
        cache = {}
    raw_rows = cache.get("events") if isinstance(cache.get("events"), list) else []
    source_checks = cache.get("sources") if isinstance(cache.get("sources"), dict) else {}
    requested = [symbol.strip().upper()] if isinstance(symbol, str) and symbol.strip() else list(ISSUERS)
    events, missing = [], []
    for ticker in requested:
        issuer = ISSUERS.get(ticker)
        entry = {"symbol": ticker, "name": issuer["name"] if issuer else ticker, "sourceUrl": issuer["url"] if issuer else None}
        if not issuer:
            missing.append({**entry, "reason": "issuer_not_covered"})
            continue
        if not issuer["host"]:
            missing.append({**entry, "reason": "official_schedule_not_collected"})
            continue
        upcoming = []
        for raw in raw_rows:
            if not isinstance(raw, dict) or raw.get("symbol") != ticker:
                continue
            try:
                row = validate_event(raw, now=now)
            except (ValueError, TypeError, KeyError):
                continue
            if parse_timestamp(row["scheduledAt"]) > now:
                upcoming.append(row)
        fresh = [row for row in upcoming if now - parse_timestamp(row["source"]["checkedAt"]) <= MAX_CHECK_AGE]
        if fresh:
            check = source_checks.get(ticker) or {}
            for row in fresh:
                row["source"]["retainedAfterCheckFailure"] = isinstance(check, dict) and check.get("status") == "error"
            events.extend(fresh)
        elif upcoming:
            missing.append({**entry, "reason": "source_check_stale", "checkedAt": max(row["source"]["checkedAt"] for row in upcoming)})
        else:
            missing.append({**entry, "reason": "no_upcoming_verified_call"})
    unique = {row["id"]: row for row in events}
    events = sorted(unique.values(), key=lambda row: (row["scheduledAt"], row["symbol"]))
    checked = [row["source"]["checkedAt"] for row in events]
    return {
        "schemaVersion": SCHEMA_VERSION, "generatedAt": cache.get("generatedAt"),
        "checkedAt": min(checked) if checked else None, "cacheMode": "static",
        "status": "partial" if events else "unavailable", "events": events,
        "coverage": {"trackedSymbols": requested, "scheduledSymbols": sorted({row["symbol"] for row in events}), "missing": missing},
        "comparison": {"status": "unavailable", "reason": "pre_event_estimate_snapshot_not_available", "required": ["immutable_pre_event_estimate", "same_period_and_accounting_basis", "actual_publication_timestamp", "verified_regular_session_closes"]},
    }
