"""Explicitly approved, read-only archive of old 3-agent debate transcripts.

IMPORTANT: the Chart View API and Toss are public. Never ingest private
investment-intelligence-os GitHub records here, even with a GitHub token.
Only serve a local, operator-reviewed projection after owner publication approval.
Disabled by default (503); no auto-enable, no private DB or repo access.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()
MAX_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 30
ALLOWED_STAGES = {"phase1", "attack", "rebuttal", "final", "audit", "context"}
ALLOWED_ROLES = {"mer", "nonggu", "meng", "other"}
ALLOWED_STATUSES = {"COMPLETED", "PARTIAL", "BLOCKED"}
ALLOWED_VERDICTS = {"BUY", "WAIT", "SELL", "UNKNOWN"}
FORBIDDEN = ("api_key", "apikey", "password", "secret", "private_key", "token", "account", "db_path", "dsn",
             "holdings", "positions", "portfolio", "quantity", "avg_cost", "cost_basis", "user_id", "watchlist")
TICKER = re.compile(r"^[A-Z0-9.\-^]{1,18}$")

# Explicit owner approval does not replace a second conservative PII guard.
# Reject risky freeform text on the PUBLIC API. Review/redact locally first.
PRIVATE_TEXT = tuple(re.compile(p, re.I) for p in (
    r"\b010[-\s]?\d{4}[-\s]?\d{4}\b",        # Korean mobile numbers
    r"[\w.+-]+@[\w-]+\.[\w.-]+",             # email addresses
    r"\b\d{6}[- ]?[1-4]\d{6}\b",            # RRN-like identifier
    r"gh[pousr]_[a-z0-9]{20,}",              # GitHub token
    r"sk-[a-z0-9_-]{20,}",                  # API secret
    r"AKIA[A-Z0-9]{16}",                    # AWS access key
    r"(?:내|본인|현재)\s*(?:보유|투자|계좌)\s*(?:금액|잔액|평가액)?",
    r"보유\s*(?:수량|금액|비중|평단|평균단가)",
    r"(?:api[_-]?key|password|passwd|secret|access[_-]?token|token)\s*[:=]\s*[\w/+.-]{4,}",
    r"계좌(?:번호|잔액|평가액)|매입(?:수량|단가)|평균(?:매입|매수)단가|평단가",
    r"\b(?:my|personal)\s+(?:portfolio|holdings|account)\b",
))
def _safe_public_text(value: str) -> str:
    for index, pattern in enumerate(PRIVATE_TEXT):
        # Avoid quadratic backtracking on long prose with no email delimiter.
        if index == 1 and "@" not in value:
            continue
        if pattern.search(value):
            raise ValueError("possible private data in public debate text")
    return value

ID = re.compile(r"^[A-Za-z0-9_-]{3,80}$")

def _time(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone aware")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise ValueError("future timestamp")
    return parsed.isoformat()

def _str(obj, key, maximum, *, required=True):
    value = obj.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > maximum:
        raise ValueError("invalid " + key)
    return value

def _no_sensitive_keys(item):
    if isinstance(item, str):
        _safe_public_text(item)
    if isinstance(item, list):
        for i in item:
            _no_sensitive_keys(i)
    if isinstance(item, dict):
        for key, val in item.items():
            if any(word in str(key).lower() for word in FORBIDDEN):
                raise ValueError("private key field in archive")
            _no_sensitive_keys(val)

def public_archive(doc: dict) -> dict:
    if not isinstance(doc, dict) or doc.get("schema_version") != 1 or doc.get("kind") != "debate_archive" or doc.get("publication_status") != "EXPLICITLY_APPROVED":
        raise ValueError("debate archive not explicitly approved")
    generated = _time(doc.get("generated_at"))
    _no_sensitive_keys(doc)
    entries = doc.get("debates")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise ValueError("invalid number of debates")
    ids = set()
    sanitized = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid debate")
        key = _str(entry, "id", 80)
        if not ID.fullmatch(key) or key in ids:
            raise ValueError("duplicate/invalid debate id")
        ids.add(key)
        date = _str(entry, "date", 10)
        try:
            if datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
                raise ValueError("bad date")
        except ValueError as exc:
            raise ValueError("bad date") from exc
        ticker = _str(entry, "ticker", 18)
        if not TICKER.fullmatch(ticker):
            raise ValueError("bad ticker")
        status = entry.get("status")
        verdict = entry.get("verdict")
        if status not in ALLOWED_STATUSES or verdict not in ALLOWED_VERDICTS or entry.get("audit_verified") is not False:
            raise ValueError("old debate must remain unaudited archive only")
        phases = entry.get("phases")
        if not isinstance(phases, list) or not 1 <= len(phases) <= 24:
            raise ValueError("invalid phase count")
        cleaned_phases = []
        for phase in phases:
            if not isinstance(phase, dict) or phase.get("role") not in ALLOWED_ROLES or phase.get("stage") not in ALLOWED_STAGES:
                raise ValueError("invalid debate phase")
            src = _str(phase, "source_path", 260)
            parts = PurePosixPath(src).parts
            if not src.endswith(".md") or len(parts) < 3 or parts[:2] not in (("records", "debates"), ("records", "shadow")) or ".." in parts or "\\" in src:
                raise ValueError("unexpected source path")
            cleaned_phases.append({
                "role": phase["role"], "stage": phase["stage"],
                "title": _str(phase, "title", 160),
                "text": _safe_public_text(_str(phase, "text", 16000)),
                "source_path": src,
            })
        extension = {}
        if "summary" in entry or "updated_at" in entry:
            summary = _str(entry, "summary", 600)
            updated_at = _time(entry.get("updated_at"))
            if datetime.fromisoformat(updated_at) > datetime.fromisoformat(generated):
                raise ValueError("research update after publication")
            if status == "COMPLETED":
                participants = {p["role"] for p in cleaned_phases if p["stage"] == "phase1"}
                stages = {p["stage"] for p in cleaned_phases}
                if not {"mer", "nonggu", "meng"} <= participants or not {"attack", "rebuttal", "final"} <= stages:
                    raise ValueError("completed research requires three agents and final rounds")
            extension = {"summary": summary, "updated_at": updated_at}
        sanitized.append({
            "id": key, "date": date, "company": _str(entry, "company", 100),
            "ticker": ticker, "topic": _str(entry, "topic", 240, required=False),
            "status": status, "verdict": verdict, "audit_verified": False,
            "phases": cleaned_phases, **extension,
        })
    return {
        "schema_version": 1, "kind": "debate_archive",
        "publication_status": "EXPLICITLY_APPROVED", "generated_at": generated,
        "debates": sanitized,
    }

def load_archive():
    path = os.environ.get("INTEL_DEBATE_FEED_PATH", "").strip()
    if not path or not Path(path).is_absolute():
        raise RuntimeError("debate archive not approved/configured")
    with Path(path).open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("debate archive too large")
    document = public_archive(json.loads(content))
    raw = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    etag = '"' + hashlib.sha256(raw).hexdigest()[:32] + '"'
    return document, etag

@router.get("/api/intelligence/debates")
def intelligence_debates(request: Request):
    try:
        doc, etag = load_archive()
    except (RuntimeError, OSError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail="Approved debate archive unavailable")
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60", "X-Archive-Mode": "UNVERIFIED_HISTORY"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=doc, headers=headers)


# Aggregate Shadow-mode metrics are OFF until separately approved.
SHADOW_KEYS = ("runs_total", "screenings_total", "debates_total",
               "audits_approved", "audits_blocked", "failures_total",
               "smoke_runs_total", "smoke_audits_approved")
SHADOW_STATES = {"NOT_STARTED", "RUNNING", "PAUSED", "STOPPED"}

def public_shadow_status(doc: dict) -> dict:
    if not isinstance(doc, dict) or doc.get("schema_version") != 1 or \
       doc.get("kind") != "shadow_status" or \
       doc.get("publication_status") != "EXPLICITLY_APPROVED":
        raise ValueError("status not publicly approved")
    _no_sensitive_keys(doc)
    generated_at = _time(doc.get("generated_at"))
    state = doc.get("state")
    if state not in SHADOW_STATES:
        raise ValueError("invalid state")
    started_at = doc.get("period_started_at")
    last_at = doc.get("last_execution_at")
    if started_at is not None:
        started_at = _time(started_at)
    if last_at is not None:
        last_at = _time(last_at)
    if state == "RUNNING" and (started_at is None or last_at is None):
        raise ValueError("RUNNING requires actual execution timestamps")
    values = {}
    for key in SHADOW_KEYS:
        val = doc.get(key)
        if isinstance(val, bool) or not isinstance(val, int) or val < 0 or val > 10000000:
            raise ValueError("invalid aggregate value: "+key)
        values[key] = val
    if values["audits_approved"] + values["audits_blocked"] > values["debates_total"]:
        raise ValueError("inconsistent audit totals")
    if values["smoke_audits_approved"] > values["smoke_runs_total"]:
        raise ValueError("inconsistent smoke totals")
    if started_at and last_at and datetime.fromisoformat(last_at) < datetime.fromisoformat(started_at):
        raise ValueError("last execution before start")
    return {"schema_version": 1, "kind": "shadow_status",
            "publication_status": "EXPLICITLY_APPROVED",
            "generated_at": generated_at, "state": state,
            "period_started_at": started_at,
            "last_execution_at": last_at, **values}


@router.get("/api/intelligence/shadow/status")
def intelligence_shadow_status(request: Request):
    source = os.environ.get("INTEL_SHADOW_STATUS_PATH", "").strip()
    if not source or not Path(source).is_absolute():
        raise HTTPException(status_code=503, detail="Shadow status not configured")
    try:
        with Path(source).open("rb") as fh:
            raw_content = fh.read(16385)
        if len(raw_content) > 16384:
            raise ValueError("status file exceeds 16KiB")
        doc = public_shadow_status(json.loads(raw_content))
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
        etag = '"' + hashlib.sha256(raw).hexdigest()[:32] + '"'
    except (OSError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail="Approved Shadow status unavailable")
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60",
               "X-Archive-Mode": "AGGREGATED_SHADOW_ONLY"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=doc, headers=headers)
