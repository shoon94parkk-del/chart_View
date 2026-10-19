"""Read-only, opt-in public research feed from a trusted local projection.

Only the verified privacy-minimized projection may be exposed. No external
fetching, private Muse repo access, database reads or LLM requests on GET.
By default the route returns 503 until the operator configures a local file.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()
MAX_FILE_BYTES = 512 * 1024
MAX_CANDIDATES = 50
MAX_EVENTS = 100


def _timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("missing timezone-aware as_of")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("bad as_of") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("naive as_of")
    return parsed.isoformat()


def public_projection(document: dict) -> dict:
    """Allowlist everything. Unknown/private payload members never leave host."""
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("unsupported schema")
    if document.get("kind") != "market_research" or document.get("publication_status") != "RESEARCH_ONLY":
        raise ValueError("not a public research projection")
    as_of = _timestamp(document.get("as_of"))
    from datetime import timedelta
    if datetime.fromisoformat(as_of).astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise ValueError("future as_of")
    if document.get("coverage_status") not in ("COMPLETE", "PARTIAL_COVERAGE"):
        raise ValueError("bad coverage")
    if document.get("quality_status") not in ("COMPLETE", "PARTIAL_DATA"):
        raise ValueError("bad data quality")
    if document.get("picks") != [] or document.get("pick_history") != []:
        raise ValueError("unverified picks must not be publicly exposed")
    candidates, events = document.get("candidates"), document.get("market_events")
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError("bad candidates")
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError("bad market_events")
    safe_candidates = []
    for row in candidates:
        if not isinstance(row, dict) or not isinstance(row.get("ticker"), str):
            raise ValueError("bad candidate")
        score = row.get("score")
        if (type(score) not in (float, int) or not math.isfinite(score)
                or not 0 <= score <= 100 or row.get("buy_eligible") is not False
                or row.get("stage") != "DISCOVERED"
                or row.get("market") not in ("KR", "US")):
            raise ValueError("candidate not approved for research view")
        import re
        if not re.fullmatch(r"[A-Z0-9.\-^]{1,18}", row["ticker"]):
            raise ValueError("invalid ticker")
        safe_candidates.append({
            "ticker": row["ticker"], "market": row["market"],
            "stage": "DISCOVERED", "buy_eligible": False,
            "score": score,
        })
    safe_events = []
    for row in events:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or len(row["id"]) > 180 or row.get("action") != "REVIEW_ONLY"
                or row.get("requires_review") is not True
                or row.get("severity") not in ("CRITICAL", "WARNING")):
            raise ValueError("unsafe event")
        safe_events.append({
            # External clients do not need private/original upstream IDs.
            "id": "MARKET:" + hashlib.sha256(row["id"].encode("utf-8")).hexdigest()[:24],
            "severity": row["severity"],
            "action": "REVIEW_ONLY", "requires_review": True,
        })
    return {
        "schema_version": 1, "kind": "market_research",
        "publication_status": "RESEARCH_ONLY", "as_of": as_of,
        "coverage_status": document["coverage_status"],
        "quality_status": document["quality_status"],
        "candidates": safe_candidates, "market_events": safe_events,
        "picks": [], "pick_history": [],
    }


def load_feed() -> dict:
    path = os.environ.get("MARKET_INTELLIGENCE_FEED_PATH", "").strip()
    if not path or not Path(path).is_absolute():
        raise RuntimeError("feed not configured")
    target = Path(path)
    with target.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("feed too large")
    return public_projection(json.loads(data.decode("utf-8")))


@router.get("/api/intelligence/feed")
def intelligence_feed(request: Request):
    """Safe to ship disabled; operator must configure a verified projection."""
    try:
        doc = load_feed()
    except (OSError, UnicodeError, ValueError, RuntimeError, TypeError):
        raise HTTPException(status_code=503, detail="시장 조사 데이터 준비 중")
    raw = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    etag = '"' + hashlib.sha256(raw).hexdigest()[:24] + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(doc, headers=headers)
