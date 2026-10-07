"""Validated warm-start material for the existing canonical full heatmap cache.

This is not a quote provider or a freshness cache. Observation dates and quote
provenance survive unchanged, and every retained snapshot row is marked stale.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SNAPSHOT_VERSION = 1
MAX_SNAPSHOT_AGE = timedelta(hours=48)
MAX_SNAPSHOT_BYTES = 1024 * 1024
CANONICAL_BASES = {"provider-canonical", "home-canonical"}


class SnapshotValidationError(ValueError):
    """The complete file is rejected; no invalid rows are silently promoted."""


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotValidationError(f"{field} needs an observation timestamp")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotValidationError(f"invalid {field}") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise SnapshotValidationError(f"{field} needs an explicit timezone")
    return instant.astimezone(timezone.utc)


def _number(value: Any, field: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SnapshotValidationError(f"{field} must be a JSON number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (positive and value <= 0):
        raise SnapshotValidationError(f"invalid {field}")


def _session(value: Any, field: str) -> date | None:
    # Some canonical Home quotes do not expose session fields. Never fabricate
    # them from the capture date; asOf is independently mandatory.
    if value is None:
        return None
    if not isinstance(value, str):
        raise SnapshotValidationError(f"invalid {field}")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise SnapshotValidationError(f"invalid {field}") from exc
    if result.isoformat() != value:
        raise SnapshotValidationError(f"invalid {field}")
    return result


def _validate_row(row: Any, captured_at: datetime) -> datetime:
    if not isinstance(row, dict):
        raise SnapshotValidationError("snapshot rows must be objects")
    ticker, market = row.get("ticker"), row.get("market")
    if not isinstance(ticker, str) or not ticker or ticker != ticker.strip().upper():
        raise SnapshotValidationError("invalid ticker")
    if market not in {"KR", "US"} or (market == "KR") != ticker.endswith((".KS", ".KQ")):
        raise SnapshotValidationError(f"invalid market for {ticker}")
    if row.get("quoteBasis") not in CANONICAL_BASES:
        raise SnapshotValidationError(f"noncanonical quote for {ticker}")
    source = row.get("source")
    if not isinstance(source, str) or not source.strip() or "legacy" in source.lower():
        raise SnapshotValidationError(f"missing canonical source for {ticker}")
    for field in ("price", "marketCap", "change"):
        _number(row.get(field), f"{ticker}.{field}", positive=field != "change")
    observed_at = _instant(row.get("asOf"), f"{ticker}.asOf")
    if observed_at > captured_at:
        raise SnapshotValidationError(f"future observation for {ticker}")
    session = _session(row.get("sessionDate"), f"{ticker}.sessionDate")
    previous = _session(row.get("previousSessionDate"), f"{ticker}.previousSessionDate")
    local_observation = observed_at.astimezone(ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")).date()
    if session and session > local_observation:
        raise SnapshotValidationError(f"future session for {ticker}")
    if previous and ((session and previous >= session) or previous >= local_observation):
        raise SnapshotValidationError(f"invalid previous session for {ticker}")
    if "stale" in row and not isinstance(row["stale"], bool):
        raise SnapshotValidationError(f"invalid stale flag for {ticker}")
    return observed_at


def eligible_markets(kr_tickers: list[str], us_rows: list[dict]) -> dict[str, str]:
    """Use the caller's current universe, never expand the 20/40 quote budget."""
    return {**{ticker: "KR" for ticker in kr_tickers},
            **{row["ticker"]: "US" for row in us_rows}}


def validate_snapshot(payload: Any, eligible: dict[str, str], *, now: datetime | None = None,
                      require_complete: bool = False) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SnapshotValidationError("validation time needs a timezone")
    if not isinstance(payload, dict) or type(payload.get("snapshotVersion")) is not int or payload.get("snapshotVersion") != SNAPSHOT_VERSION:
        raise SnapshotValidationError("unsupported full heatmap snapshot")
    captured_at = _instant(payload.get("snapshotCapturedAt"), "snapshotCapturedAt")
    generated_at = _instant(payload.get("generatedAt"), "generatedAt")
    for label, instant in (("snapshotCapturedAt", captured_at), ("generatedAt", generated_at)):
        if instant > now or now - instant > MAX_SNAPSHOT_AGE:
            raise SnapshotValidationError(f"{label} is future or older than 48 hours")
    if generated_at > captured_at:
        raise SnapshotValidationError("snapshot precedes the API generation time")
    if not str(payload.get("source") or "").startswith("canonical-"):
        raise SnapshotValidationError("snapshot must come from the canonical full heatmap API")
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows or len(rows) > 60:
        raise SnapshotValidationError("invalid full heatmap rows")
    seen, retained = set(), []
    actual_counts = {"KR": 0, "US": 0}
    for row in rows:
        observed_at = _validate_row(row, captured_at)
        ticker = row["ticker"]
        if ticker in seen:
            raise SnapshotValidationError(f"duplicate ticker {ticker}")
        seen.add(ticker)
        actual_counts[row["market"]] += 1
        # A changed universe or an individually expired observation is omitted.
        # Malformed rows above still invalidate the entire file, even if omitted.
        if eligible.get(ticker) == row["market"] and now - observed_at <= MAX_SNAPSHOT_AGE:
            retained.append({**row, "stale": True})
    if actual_counts["KR"] > 20 or actual_counts["US"] > 40:
        raise SnapshotValidationError("snapshot exceeds the canonical 20/40 budget")
    counts = payload.get("counts")
    if not isinstance(counts, dict) or any(type(counts.get(market)) is not int for market in ("KR", "US")) or counts != actual_counts:
        raise SnapshotValidationError("API counts do not match the snapshot rows")
    if require_complete and (payload.get("complete") is not True or set(eligible) != {row["ticker"] for row in retained}):
        raise SnapshotValidationError("API has not returned the complete current eligible universe")
    if not retained:
        raise SnapshotValidationError("snapshot has no recent eligible observations")
    return {**payload, "results": retained,
            "counts": {market: sum(row["market"] == market for row in retained) for market in ("KR", "US")},
            "complete": set(eligible) == {row["ticker"] for row in retained}}


def load_snapshot(path: str | Path, eligible: dict[str, str], *, now: datetime | None = None) -> dict | None:
    try:
        path = Path(path)
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            return None
        return validate_snapshot(json.loads(path.read_text(encoding="utf-8")), eligible, now=now)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        return None


def merge_seed_rows(snapshot_rows: list[dict], current_rows: list[dict], eligible: dict[str, str]) -> list[dict]:
    """Keep newer canonical observations; equal/unknown current timestamps win.

    Existing daily screener fallback is not a verified canonical quote. A recent
    validated snapshot can replace that fallback, but never a newer Home quote.
    """
    merged = {row["ticker"]: {**row, "stale": True} for row in snapshot_rows
              if eligible.get(row.get("ticker")) == row.get("market")}
    for row in current_rows:
        ticker = row.get("ticker")
        if eligible.get(ticker) != row.get("market"):
            continue
        candidate = merged.get(ticker)
        if candidate and row.get("quoteBasis") not in CANONICAL_BASES:
            continue
        if candidate:
            try:
                if _instant(candidate.get("asOf"), "asOf") > _instant(row.get("asOf"), "asOf"):
                    continue
            except SnapshotValidationError:
                pass
        merged[ticker] = row
    return [merged[ticker] for ticker in eligible if ticker in merged]
