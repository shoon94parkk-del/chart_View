"""Public, read-only investment news; independent of audited PICK/decisions.

Only a bounded public projection is served. No collection, model, Telegram,
private database or trading work runs on this request path.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from debate_archive_service import FORBIDDEN, PRIVATE_TEXT

router = APIRouter()
FILENAME = "intelligence_investment_news.json"
MAX_BYTES = 4 * 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:\-]{1,120}$")
_SYMBOL = re.compile(r"^[A-Z0-9.^=\-]{1,30}$")
_KST = timezone(timedelta(hours=9))
_UNSUPPORTED_RETURN_ALIASES = {"return_pct", "benchmark_return_pct", "excess_return_pct", "mdd_pct"}
_EXTRA_PRIVATE = {"chat_id", "chatid", "raw_text", "raw_content", "raw_article", "raw_prompt", "system_prompt", "audit_trail", "chain_of_thought", "private_thesis", "personal_thesis"}
# A company article slug such as sk-telecom-and-hana-... is not an API key.
# Preserve classic contiguous and modern project/service-account key guards.
_API_KEY = re.compile(r"\bsk-(?:(?:proj-|svcacct-)[a-z0-9_-]{20,}|[a-z0-9_]{20,}(?![a-z0-9_-]))", re.I)


def _text(value, *, maximum=1200, required=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError("invalid public news text")
    return value


def _list(value, maximum=1000):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("invalid public news list")
    return value


def _texts(value, *, maximum=20, text_max=600):
    return [_text(item, maximum=text_max, required=True) for item in _list(value, maximum)]


def _time(value, *, nullable=False, utc=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError("missing news timestamp")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid news timestamp") from exc
    if date.tzinfo is None or date.utcoffset() is None or (utc and date.utcoffset() != timedelta(0)):
        raise ValueError("news timestamp must have the required timezone")
    if date.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise ValueError("future news timestamp")
    return value


def _date(value):
    if not isinstance(value, str):
        raise ValueError("missing news date")
    try:
        if datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
            raise ValueError("invalid news date")
    except ValueError as exc:
        raise ValueError("invalid news date") from exc
    return value


def _number(value, *, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("invalid public news number")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError("public news number outside range")
    return value


def _url(value):
    _text(value, maximum=1800, required=True)
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if (value != value.strip() or url.scheme != "https" or not host or url.username or url.password
                or url.port not in (None, 443) or any(host == domain or host.endswith("." + domain) for domain in ("t.me", "telegram.me", "telegram.org", "telegram.dog"))):
            raise ValueError("unsafe source URL")
        if any(re.search(r"api.?key|token|password|secret|signature", key, re.I) for key, _ in parse_qsl(url.query, keep_blank_values=True)):
            raise ValueError("credential-bearing source URL")
    except ValueError as exc:
        raise ValueError("unsafe source URL") from exc
    return value


def _scan(value):
    def visit(item):
        if isinstance(item, str):
            for index, pattern in enumerate(PRIVATE_TEXT):
                if index == 1 and "@" not in item:
                    continue
                if (_API_KEY if index == 4 else pattern).search(item):
                    raise ValueError("possible private data in public news")
        elif isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in _EXTRA_PRIVATE or any(fragment in str(key).lower() for fragment in FORBIDDEN):
                    raise ValueError("private news field")
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)


def _metadata(value, fields):
    """Small declared public metadata; never forward arbitrary producer state."""
    if not isinstance(value, dict):
        raise ValueError("invalid public metadata")
    out = {}
    for key, entry in value.items():
        if key not in fields:
            continue
        if entry is None or isinstance(entry, bool):
            out[key] = entry
        elif isinstance(entry, (int, float)):
            out[key] = _number(entry)
        elif isinstance(entry, str):
            if key.endswith("_at"):
                out[key] = _time(entry)
            else:
                out[key] = _text(entry, maximum=600)
        elif isinstance(entry, list):
            out[key] = _texts(entry, maximum=50, text_max=600)
        else:
            raise ValueError("unexpected nested public metadata")
    return out


COLLECTION_FIELDS = {"status", "sources_total", "sources_ok", "sources_failed", "failed_sources", "events_total", "last_success_at", "last_failure_at", "last_error_at", "last_attempt_at", "last_run_at", "started_at", "heartbeat_at", "message", "checked_at", "baseline", "source_count", "success_count", "error_count", "total_sources", "successful_sources"}
CAPABILITY_FIELDS = {"ai_analysis", "telegram_delivery", "telegram_input", "thesis_context", "performance", "collection", "official_sources", "ai", "telegram", "notifications", "price_outcomes", "thesis_reviews", "live_prices", "ai_configured", "telegram_configured", "telegram_input_enabled"}


def _collection(value):
    result = _metadata(value, COLLECTION_FIELDS)
    if "sources" in value:
        result["sources"] = [_metadata(source, {"source_id", "last_success_at", "last_failure_at", "last_attempt_at", "count", "last_count", "error", "last_error", "consecutive_failures"}) for source in _list(value["sources"], 100)]
    if "errors" in value:
        result["errors"] = [_metadata(error, {"source_id", "error"}) if isinstance(error, dict) else _text(error, maximum=600) for error in _list(value["errors"], 100)]
    return result


def _agents(value):
    if not isinstance(value, dict) or set(value) - {"mer", "nonggu", "meng"}:
        raise ValueError("invalid news roles")
    result = {}
    for role, entry in value.items():
        clean = _metadata(entry, {"role", "status", "summary", "claims", "risks", "conditions", "horizon", "conclusion", "error", "analysis_status", "model", "direction", "input_digest", "evidence_ids", "invalidators", "unknowns", "next_checks"})
        for key in ("role", "status", "summary", "horizon", "conclusion", "error", "analysis_status", "model", "direction", "input_digest"):
            if key in clean:
                clean[key] = _text(clean[key], maximum=600)
        for key in ("claims", "risks", "conditions", "evidence_ids", "invalidators", "unknowns", "next_checks"):
            if key in clean:
                clean[key] = _texts(clean[key], maximum=50)
        if "role" in clean and clean["role"] != role:
            raise ValueError("mismatched news role")
        if "direction" in clean and clean["direction"] not in ("positive", "negative", "mixed", "unknown"):
            raise ValueError("invalid agent direction")
        if "inferences" in entry:
            clean["inferences"] = []
            for inference in _list(entry["inferences"], 10):
                item = _metadata(inference, {"text", "condition", "horizon", "evidence_ids"})
                if set(item.get("evidence_ids", [])) - set(clean.get("evidence_ids", [])):
                    raise ValueError("inference must cite agent evidence")
                clean["inferences"].append(item)
        result[role] = clean
    return result


def _briefing(value):
    result = _metadata(value, {"date", "as_of_date", "generated_at", "title", "summary", "event_ids", "newly_confirmed", "coverage_note", "status", "briefing_id", "trade_action"})
    if result.get("trade_action") != "REVIEW_ONLY":
        raise ValueError("briefing is review only")
    if "date" in result:
        _date(result["date"])
    for key in ("event_ids", "newly_confirmed"):
        if any(not _IDENTIFIER.fullmatch(identifier) for identifier in result.get(key, [])):
            raise ValueError("invalid briefing event identity")
    if "changed_since_previous" in value:
        result["changed_since_previous"] = []
        for change in _list(value["changed_since_previous"], 100):
            item = _metadata(change, {"event_id", "revision"})
            revision = item.get("revision")
            if not _IDENTIFIER.fullmatch(str(item.get("event_id", ""))) or isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
                raise ValueError("invalid briefing revision")
            result["changed_since_previous"].append(item)
    if "connections" in value:
        result["connections"] = []
        for connection in _list(value["connections"], 100):
            item = _metadata(connection, {"sector", "event_ids", "text", "verification"})
            if item.get("verification") != "inference" or any(not _IDENTIFIER.fullmatch(identifier) for identifier in item.get("event_ids", [])):
                raise ValueError("briefing connections remain inferences")
            result["connections"].append(item)
    return result


def _event(event):
    if not isinstance(event, dict):
        raise ValueError("invalid news event")
    identifier = _text(event.get("event_id"), maximum=120, required=True)
    revision = event.get("revision")
    if not _IDENTIFIER.fullmatch(identifier) or isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("invalid news identity")
    if event.get("trade_action") != "REVIEW_ONLY":
        raise ValueError("news is review only")
    sources = []
    for source in _list(event.get("sources"), 30):
        if not isinstance(source, dict):
            raise ValueError("invalid news source")
        sources.append({"name": _text(source.get("name"), maximum=120, required=True), "url": _url(source.get("url")),
                        "published_at": _time(source.get("published_at"), nullable=True), "retrieved_at": _time(source.get("retrieved_at")),
                        "kind": _text(source.get("kind"), maximum=80, required=True),
                        "independent_group": _text(source.get("independent_group"), maximum=120)})
    if not sources:
        raise ValueError("event requires public source evidence")
    source_urls = {source["url"] for source in sources}
    facts = []
    for fact in _list(event.get("facts", []), 30):
        if not isinstance(fact, dict) or fact.get("source_url") not in source_urls:
            raise ValueError("fact must cite the event evidence")
        numbers = _list(fact.get("numbers", []), 500)
        facts.append({"text": _text(fact.get("text"), required=True), "source_url": _url(fact["source_url"]),
                      "verification": _text(fact.get("verification", "unknown"), maximum=80),
                      "numbers": [_text(n, maximum=120) if isinstance(n, str) else _number(n) for n in numbers]})
    inferences = []
    for item in _list(event.get("inferences", []), 30):
        if not isinstance(item, dict):
            raise ValueError("invalid inference")
        inferences.append({"text": _text(item.get("text"), required=True), "condition": _text(item.get("condition")), "horizon": _text(item.get("horizon"), maximum=80)})
    tickers = []
    for ticker in _list(event.get("tickers", []), 50):
        if not isinstance(ticker, dict) or not _SYMBOL.fullmatch(str(ticker.get("symbol", ""))) or ticker.get("market") not in ("KR", "US", "GLOBAL", "UNKNOWN"):
            raise ValueError("invalid news ticker")
        tickers.append({"symbol": ticker["symbol"], "name": _text(ticker.get("name"), maximum=120), "market": ticker["market"]})
    sentiment = event.get("sentiment", "unknown")
    if sentiment not in ("positive", "negative", "mixed", "unknown"):
        raise ValueError("invalid news sentiment")
    safe_agents = _agents(event.get("agents", {}))
    analysis_status = _text(event.get("analysis_status", "unavailable"), maximum=80)
    if analysis_status == "completed" and (set(safe_agents) != {"mer", "nonggu", "meng"} or any(not agent.get("summary") or not agent.get("evidence_ids") for agent in safe_agents.values())):
        raise ValueError("completed analysis requires three evidenced agents")
    reviews = [_metadata(review, {"ticker", "thesis_id", "symbol", "status", "summary", "reason", "reviewed_at", "event_id", "evidence_urls", "change", "previous_status", "current_status"}) for review in _list(event.get("thesis_reviews", []), 50)]
    for review in reviews:
        for url in _list(review.get("evidence_urls", []), 50):
            _url(url)
    # Only evidence-backed outcomes supplied by the producer are public. Empty
    # outcomes remain empty; no response-time price/return is ever invented.
    performance = []
    for item in _list(event.get("performance", []), 30):
        if isinstance(item, dict) and _UNSUPPORTED_RETURN_ALIASES.intersection(item):
            raise ValueError("news returns use canonical fractional fields")
        performance.append(_metadata(item, {"ticker", "symbol", "market", "horizon", "status", "as_of", "as_of_date", "analysis_at", "baseline_at", "followup_at", "evaluated_at", "price_date", "benchmark", "stock_return", "benchmark_return", "excess_return", "baseline_price", "close_price", "source_urls", "source_url", "benchmark_source_url", "currency"}))
    for outcome in performance:
        for key in ("stock_return", "benchmark_return", "excess_return", "baseline_price", "close_price"):
            if outcome.get(key) is not None:
                outcome[key] = _number(outcome[key])
        for url in _list(outcome.get("source_urls", []), 50):
            _url(url)
        for key in ("source_url", "benchmark_source_url"):
            if outcome.get(key) is not None:
                _url(outcome[key])
        if any(outcome.get(key) is not None for key in ("stock_return", "benchmark_return", "excess_return")) and (not outcome.get("baseline_at") or not outcome.get("followup_at") or not outcome.get("source_urls")):
            raise ValueError("returns require observed dates and sources")
        if outcome.get("baseline_at") and outcome.get("followup_at") and datetime.fromisoformat(outcome["followup_at"].replace("Z", "+00:00")) < datetime.fromisoformat(outcome["baseline_at"].replace("Z", "+00:00")):
            raise ValueError("return observation window is reversed")
    return {"event_id": identifier, "revision": revision, "title": _text(event.get("title"), maximum=300, required=True),
            "published_at": _time(event.get("published_at"), nullable=True), "first_seen_at": _time(event.get("first_seen_at")), "updated_at": _time(event.get("updated_at")),
            "summary": _texts(event.get("summary", []), maximum=8),
            **{key: _number(event.get(key), low=0, high=100) for key in ("importance", "confidence", "novelty", "market_impact")},
            "sectors": _texts(event.get("sectors", []), maximum=30, text_max=120), "tickers": tickers, "sentiment": sentiment,
            "facts": facts, "inferences": inferences, "sources": sources,
            "verification_status": _text(event.get("verification_status", "unknown"), maximum=80),
            "expectation_status": _text(event.get("expectation_status", "unknown"), maximum=80),
            "thesis_status": _text(event.get("thesis_status", "no_context"), maximum=80), "thesis_reviews": reviews,
            "analysis_status": analysis_status, "agents": safe_agents,
            "trade_action": "REVIEW_ONLY", "performance": performance}


def public_news(doc):
    """Validate and rebuild only the public investment-news.v1 contract."""
    if not isinstance(doc, dict) or doc.get("schemaVersion") != "investment-news.v1" or doc.get("status") not in ("READY", "PARTIAL", "NOT_STARTED"):
        raise ValueError("invalid public news schema")
    raw = json.dumps(doc, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("news publication too large")
    _scan(doc)
    generated = _time(doc.get("generated_at"), utc=True)
    as_of = _date(doc.get("as_of_date"))
    if datetime.fromisoformat(generated.replace("Z", "+00:00")).astimezone(_KST).date().isoformat() != as_of:
        raise ValueError("news as-of date must match the KST publication day")
    events = [_event(event) for event in _list(doc.get("events"))]
    if len({event["event_id"] for event in events}) != len(events):
        raise ValueError("duplicate news event")
    if doc["status"] == "NOT_STARTED" and events:
        raise ValueError("not-started news cannot claim events")
    briefings = [_briefing(item) for item in _list(doc.get("briefings"), 100)]
    capabilities = _metadata(doc.get("capabilities"), CAPABILITY_FIELDS)
    if any(not isinstance(value, bool) for value in capabilities.values()) or any(capabilities.get(key) is True for key in ("telegram_input", "telegram_input_enabled")):
        raise ValueError("invalid news capabilities")
    return {"schemaVersion": "investment-news.v1", "generated_at": generated, "as_of_date": as_of,
            "status": doc["status"], "collection": _collection(doc.get("collection")),
            "capabilities": capabilities, "events": events, "briefings": briefings}


@router.get("/api/intelligence/news")
async def intelligence_news():
    from published_data import get_published_data
    try:
        document, source = await asyncio.to_thread(get_published_data, FILENAME)
        document = public_news(document)
    except (ValueError, TypeError, OSError, RuntimeError, UnicodeError):
        raise HTTPException(status_code=503, detail="Public investment news unavailable")
    return JSONResponse(document, headers={"Cache-Control": "no-store, max-age=0, must-revalidate",
                                          "X-ChartView-Data-Source": source, "X-ChartView-Data-AsOf": document["generated_at"]})
