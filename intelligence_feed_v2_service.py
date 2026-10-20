"""Audited 3-agent PICK feed (v2) — read-only, opt-in public endpoint.

Serves the v2 feed document produced by the Investment Intelligence OS
``integration/feed_v2.py`` builder (the feed contract lives in intel-os
``docs/FEED_V2_CONTRACT.md``; the companion producer PR is intel-os #11).
Only picks that passed the independent audit gate (``audit_status == "PASS"``)
may appear here.

Trust model:
- Ledger verification happens in the *publisher* (intel-os): each pick is
  resolved from the PICK ledger → decision ledger → audit registry, and only
  ledger-verified fields reach the feed file. This host never touches those
  ledgers, the Muse DB, or any private repo.
- This server re-validates every document against the v2 allowlist before
  serving it. A forged document that merely carries a bare ``"PASS"`` string
  is rejected: ``fact_pack_hash`` and ``audit_hash`` must both be present and
  every pick must survive the full contract check. The serialized document
  is additionally scanned for forbidden private key names (``api_key``,
  ``secret``, ...) — a hit refuses publication instead of being stripped,
  because it signals a pipeline leak.
- Stale snapshots are never disguised as fresh analysis: ``as_of`` and
  ``generated_at`` are always exposed, and when ``generated_at`` is older
  than the staleness threshold the response carries ``X-Feed-Stale: true``.
- P5 extension fields (optional, server-computed only): ``research_score`` /
  ``judgment_score`` (0–100), ``agent_claims`` (mer/nonggu/meng summaries),
  ``performance`` (precomputed returns). They pass the same allowlist with
  type/range validation; unvalidated values are refused, never forwarded —
  the frontend must never fabricate scores or returns.

Disabled by default: the route returns 503 until the operator configures
``MARKET_INTELLIGENCE_FEED_V2_PATH`` (absolute path to a validated feed file).
This endpoint is independent of the v1 research feed
(``GET /api/intelligence/feed``): separate module, separate env var,
separate route, mutual schema rejection.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()

MAX_FILE_BYTES = 512 * 1024
DEFAULT_STALE_AFTER_SECONDS = 6 * 3600  # 6 hours
CLOCK_SKEW = timedelta(minutes=1)

SCHEMA_VERSION = 2
KIND = "market_research"
PUBLICATION_STATUS = "AUDITED_PICKS"
SOURCE = "three_agent_audited"
AUDIT_STATUS_PASS = "PASS"

TICKER_RE = re.compile(r"^[A-Z0-9.\-^]{1,18}$")
VERDICTS = ("BUY", "WAIT", "SELL")
MARKETS = ("KR", "US")
COVERAGE_STATUSES = ("COMPLETE", "PARTIAL_COVERAGE")
QUALITY_STATUSES = ("COMPLETE", "PARTIAL_DATA")
PICK_STATUSES = ("유지", "주의", "재점검", "종료")
THESIS_MAX_CHARS = 200

# P5 — optional extension fields (server-computed only).
# Mirrors intel-os integration/feed_v2.py::_build_extension.
AGENT_CLAIM_AGENTS = ("mer", "nonggu", "meng")
AGENT_CLAIM_MAX_CHARS = 500
BENCHMARK_MAX_CHARS = 32
PERFORMANCE_PCT_KEYS = ("return_pct", "mdd_pct", "excess_benchmark_pct")

# Forbidden key-name fragments — checked against key *names*, not values.
# Mirrors intel-os integration/feed_v2.py::FORBIDDEN_KEY_FRAGMENTS.
FORBIDDEN_KEY_FRAGMENTS = (
    "api_key", "apikey", "secret", "password", "token",
    "account_id", "private_key", "db_path", "dsn",
)


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"missing timezone-aware {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"bad {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"naive {field}")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + CLOCK_SKEW:
        raise ValueError(f"future {field}")
    return parsed.isoformat()


def _require_str(mapping: dict, key: str, *, field: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing {field}")
    return value


def _iter_keys(node: object):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _iter_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_keys(item)


def _scan_forbidden_keys(document: dict) -> None:
    """Fail closed on private key names anywhere in the raw document.

    Runs on the raw document *before* allowlisting: a forbidden key name
    means the projection pipeline leaked something it must not publish, so
    the document is refused rather than silently stripped.
    """
    for key in _iter_keys(document):
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
            raise ValueError(f"forbidden key in public document: {key!r}")


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return float(value)


def _project_extension(pick: dict) -> dict:
    """Validate optional server-computed extension fields (P5).

    Mirrors intel-os ``integration/feed_v2.py::_build_extension``:
    scores must be finite numbers in [0, 100]; agent claims are pinned to
    mer/nonggu/meng (1–500 chars each); performance carries only finite
    precomputed percentages plus an optional benchmark label and a
    timezone-aware as_of. Anything else fails closed — the frontend must
    never fabricate scores or returns, and the server never forwards
    unvalidated ones.
    """
    out: dict = {}
    for key in ("research_score", "judgment_score"):
        value = pick.get(key)
        if value is None:
            continue
        number = _finite_number(value, key)
        if not 0 <= number <= 100:
            raise ValueError(f"{key} out of range [0, 100]")
        out[key] = number

    claims = pick.get("agent_claims")
    if claims is not None:
        if not isinstance(claims, dict):
            raise ValueError("agent_claims must be an object")
        unknown = set(claims) - set(AGENT_CLAIM_AGENTS)
        if unknown:
            raise ValueError(f"agent_claims has unknown agents: {sorted(unknown)}")
        clean = {}
        for agent in AGENT_CLAIM_AGENTS:
            text = claims.get(agent)
            if text is None:
                continue
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"agent_claims.{agent} must be a non-empty string")
            text = text.strip()
            if len(text) > AGENT_CLAIM_MAX_CHARS:
                raise ValueError(f"agent_claims.{agent} exceeds {AGENT_CLAIM_MAX_CHARS} chars")
            clean[agent] = text
        if clean:
            out["agent_claims"] = clean

    perf = pick.get("performance")
    if perf is not None:
        if not isinstance(perf, dict):
            raise ValueError("performance must be an object")
        clean_perf: dict = {}
        for key in PERFORMANCE_PCT_KEYS:
            value = perf.get(key)
            if value is None:
                continue
            clean_perf[key] = _finite_number(value, f"performance.{key}")
        benchmark = perf.get("benchmark")
        if benchmark is not None:
            if not isinstance(benchmark, str) or not benchmark.strip():
                raise ValueError("performance.benchmark must be a non-empty string")
            clean_perf["benchmark"] = benchmark.strip()[:BENCHMARK_MAX_CHARS]
        as_of = perf.get("as_of")
        if as_of is not None:
            clean_perf["as_of"] = _timestamp(as_of, field="performance.as_of")
        if not clean_perf:
            raise ValueError("performance must carry at least one field")
        out["performance"] = clean_perf
    return out


def _project_pick(pick: dict) -> dict:
    """Validate one pick against the v2 contract and rebuild it allowlisted.

    Raises ValueError on any violation (fail closed). Unknown extra fields
    are dropped; ``source`` is always stamped, never taken from the caller.
    """
    if not isinstance(pick, dict):
        raise ValueError("pick must be an object")

    pick_id = _require_str(pick, "pick_id", field="pick_id")
    market = pick.get("market")
    if market not in MARKETS:
        raise ValueError("bad market")
    ticker = pick.get("ticker")
    if not isinstance(ticker, str) or not TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid ticker")
    verdict = pick.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError("bad verdict")

    decided_at = _timestamp(pick.get("decided_at"), field="decided_at")
    decision_date = _require_str(pick, "decision_date", field="decision_date")

    thesis = pick.get("thesis")
    if not isinstance(thesis, str) or not thesis:
        raise ValueError("missing thesis")
    if len(thesis) > THESIS_MAX_CHARS:
        raise ValueError("thesis exceeds 200 chars")

    evidence_urls = pick.get("evidence_urls")
    if not isinstance(evidence_urls, list):
        raise ValueError("evidence_urls must be a list")
    for url in evidence_urls:
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("evidence_url must be https")

    falsifiers = pick.get("falsifiers")
    if not isinstance(falsifiers, list):
        raise ValueError("falsifiers must be a list")
    safe_falsifiers = []
    for item in falsifiers:
        if (not isinstance(item, dict)
                or not isinstance(item.get("id"), str) or not item.get("id")
                or not isinstance(item.get("metric"), str)
                or not item.get("metric")):
            raise ValueError("falsifier must carry id and metric")
        safe_falsifiers.append({"id": item["id"], "metric": item["metric"]})

    # A bare "PASS" string is never enough: both hashes are required.
    fact_pack_hash = _require_str(pick, "fact_pack_hash",
                                 field="fact_pack_hash")
    audit_hash = _require_str(pick, "audit_hash", field="audit_hash")
    if pick.get("audit_status") != AUDIT_STATUS_PASS:
        raise ValueError("audit_status must be PASS")
    status = pick.get("status")
    if status not in PICK_STATUSES:
        raise ValueError("bad status")

    projected = {
        "pick_id": pick_id, "market": market, "ticker": ticker,
        "verdict": verdict, "decided_at": decided_at,
        "decision_date": decision_date, "thesis": thesis,
        "evidence_urls": list(evidence_urls),
        "falsifiers": safe_falsifiers,
        "fact_pack_hash": fact_pack_hash, "audit_hash": audit_hash,
        "audit_status": AUDIT_STATUS_PASS, "status": status,
        "source": SOURCE,
    }
    # P5: optional server-computed extension fields (validated above).
    projected.update(_project_extension(pick))
    return projected


def v2_projection(document: dict) -> dict:
    """Validate a v2 feed document and rebuild it allowlisted.

    Mirrors intel-os ``validate_feed_v2``. Raises ValueError on the first
    violation; returns the public-safe projection otherwise. v1 documents
    (schema_version 1 / RESEARCH_ONLY) are rejected here — the two
    contracts are mutually exclusive.
    """
    if not isinstance(document, dict):
        raise ValueError("document must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema")
    if document.get("kind") != KIND:
        raise ValueError("not a market_research document")
    if document.get("publication_status") != PUBLICATION_STATUS:
        raise ValueError("not an AUDITED_PICKS document")

    as_of = _timestamp(document.get("as_of"), field="as_of")
    generated_at = _timestamp(document.get("generated_at"),
                             field="generated_at")
    if document.get("coverage_status") not in COVERAGE_STATUSES:
        raise ValueError("bad coverage_status")
    if document.get("quality_status") not in QUALITY_STATUSES:
        raise ValueError("bad quality_status")

    failure = document.get("failure_state")
    failure_state = None
    if failure is not None:
        if not isinstance(failure, dict):
            raise ValueError("bad failure_state")
        for key in ("code", "message", "at"):
            _require_str(failure, key, field=f"failure.{key}")
        failure_at = _timestamp(failure["at"], field="failure.at")
        failure_state = {"code": failure["code"],
                         "message": failure["message"], "at": failure_at}

    _scan_forbidden_keys(document)

    picks = document.get("picks")
    if not isinstance(picks, list) or not picks:
        raise ValueError("picks must be a non-empty list")

    return {
        "schema_version": SCHEMA_VERSION, "kind": KIND,
        "publication_status": PUBLICATION_STATUS,
        "as_of": as_of, "generated_at": generated_at,
        "run_key": _require_str(document, "run_key", field="run_key"),
        "coverage": _require_str(document, "coverage", field="coverage"),
        "coverage_status": document["coverage_status"],
        "quality_status": document["quality_status"],
        "failure_state": failure_state,
        "picks": [_project_pick(pick) for pick in picks],
    }


def etag_for(document: dict) -> str:
    """sha256-based ETag (32 hex chars), same canonical form as intel-os."""
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return '"' + hashlib.sha256(raw).hexdigest()[:32] + '"'


def _stale_after_seconds() -> int:
    try:
        return max(
            1, int(os.environ.get("MARKET_INTELLIGENCE_FEED_V2_STALE_AFTER",
                                 str(DEFAULT_STALE_AFTER_SECONDS))))
    except (TypeError, ValueError):
        return DEFAULT_STALE_AFTER_SECONDS


def load_feed_v2() -> tuple[dict, str, bool]:
    """Load, validate and allowlist the configured v2 feed file.

    Returns (projection, etag, stale). Raises RuntimeError when the endpoint
    is not configured (disabled by default) and ValueError/OSError on any
    invalid input. Callers map every failure to 503.
    """
    path = os.environ.get("MARKET_INTELLIGENCE_FEED_V2_PATH", "").strip()
    if not path or not Path(path).is_absolute():
        raise RuntimeError("v2 feed not configured")
    target = Path(path)
    with target.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("feed too large")
    doc = v2_projection(json.loads(data.decode("utf-8")))
    generated = datetime.fromisoformat(doc["generated_at"])
    stale = (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
             > timedelta(seconds=_stale_after_seconds()))
    return doc, etag_for(doc), stale


@router.get("/api/intelligence/feed/v2")
def intelligence_feed_v2(request: Request):
    """Safe to ship disabled; operator must configure a validated v2 file."""
    try:
        doc, etag, stale = load_feed_v2()
    except (OSError, UnicodeError, ValueError, RuntimeError, TypeError):
        raise HTTPException(status_code=503, detail="감사 인텔리전스 피드 준비 중")
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60"}
    if stale:
        # Never disguise an old snapshot as current analysis.
        headers["X-Feed-Stale"] = "true"
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(doc, headers=headers)
