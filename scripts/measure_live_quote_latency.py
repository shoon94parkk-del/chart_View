#!/usr/bin/env python3
"""Five sequential warm public-API reads, bracketed by exact-SHA health checks.

Uses Python's default TLS trust and urllib's inherited proxy configuration.
No fresh flag, cache flush, activity heartbeat, or forced idle is used.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
import urllib.error
import urllib.request


BASE_URL = "https://chart-view-pkv8.onrender.com"
QUOTE_TICKERS = ["005930.KS", "NVDA", "AAPL"]
ENDPOINTS = [
    ("home_live", "/api/home-live"),
    ("quotes", "/api/quotes?tickers=005930.KS,NVDA,AAPL"),
]
QUOTE_FIELDS = (
    "ticker", "name", "price", "change", "asOf", "currency", "source",
    "previousClose", "sessionDate", "previousSessionDate", "marketStatus",
    "sessionType", "priceBasis", "stale", "delayTime",
)
METADATA_FIELDS = (
    "source", "updatedAt", "marketUpdatedAt", "cacheAgeSec", "refreshing",
    "fetchedAt", "sharedCacheHits", "providerFetches", "freshRequested",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fetch(path):
    record = {"startedAt": utc_now(), "path": path}
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"Accept": "application/json", "User-Agent": "ChartView-Warm-API-Measurement/1.0"},
    )
    started = time.perf_counter()
    payload = None
    try:
        try:
            response = urllib.request.urlopen(request, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            record.update({
                "status": response.status,
                "durationMs": round((time.perf_counter() - started) * 1000, 3),
                "bodyBytes": len(body),
                "headers": {
                    "cache-control": response.headers.get("Cache-Control"),
                    "cf-cache-status": response.headers.get("CF-Cache-Status"),
                    "content-type": response.headers.get("Content-Type"),
                    "age": response.headers.get("Age"),
                },
                "sameRequestedUrl": response.geturl() == BASE_URL + path,
            })
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            record["error"] = "non-JSON response"
    except (OSError, TimeoutError) as error:
        record.update({
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
            "error": type(error).__name__,
        })
    record["completedAt"] = utc_now()
    return record, payload


def check_health(expected_sha):
    record, payload = fetch("/health")
    payload = payload if isinstance(payload, dict) else {}
    record["revision"] = payload.get("revision")
    record["valid"] = (
        record.get("status") == 200
        and record.get("sameRequestedUrl") is True
        and payload.get("status") == "ok"
        and record["revision"] == expected_sha
    )
    return record


def finite_number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and (not positive or value > 0)


def observed_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (ValueError, OverflowError):
        return False


def sample(name, path):
    record, payload = fetch(path)
    payload = payload if isinstance(payload, dict) else {}
    problems = []
    rows = payload.get("results")
    if record.get("status") != 200 or not record.get("sameRequestedUrl"):
        problems.append("HTTP status or final URL mismatch")
    if not isinstance(rows, list) or not rows:
        problems.append("missing public quote rows")
        rows = []
    tickers = []
    public_rows = []
    for row in rows:
        if not isinstance(row, dict):
            problems.append("non-object quote row")
            continue
        ticker = row.get("ticker")
        tickers.append(ticker)
        if not isinstance(ticker, str) or not ticker:
            problems.append("missing ticker")
        if not finite_number(row.get("price"), positive=True):
            problems.append("invalid price")
        if row.get("change") is not None and not finite_number(row["change"]):
            problems.append("invalid daily change")
        if not observed_timestamp(row.get("asOf")):
            problems.append("missing or unqualified provider observation time")
        if not isinstance(row.get("source"), str) or not row["source"]:
            problems.append("missing quote source")
        public_rows.append({key: row[key] for key in QUOTE_FIELDS if key in row})
    if len({str(ticker) for ticker in tickers}) != len(tickers):
        problems.append("duplicate ticker")
    if name == "quotes":
        if tickers != QUOTE_TICKERS or payload.get("errors") != []:
            problems.append("requested quote rows incomplete, reordered, or errored")
        counters = [payload.get("sharedCacheHits"), payload.get("providerFetches")]
        if not all(type(value) is int and value >= 0 for value in counters):
            problems.append("invalid cache/provider counters")
        elif sum(counters) != len(QUOTE_TICKERS):
            problems.append("cache/provider counters do not cover requested tickers")
        if payload.get("freshRequested") is not False:
            problems.append("unexpected fresh request semantics")
    record.update({
        "valid": not problems,
        "validationProblems": sorted(set(problems)),
        "rowCount": len(rows),
        "metadata": {key: payload[key] for key in METADATA_FIELDS if key in payload},
        "quotes": public_rows,
    })
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha):
        parser.error("--expected-sha must be a full 40-character lowercase Git SHA")
    result = {
        "startedAt": utc_now(),
        "baseUrl": BASE_URL,
        "expectedSha": args.expected_sha,
        "method": {
            "transport": "stdlib urllib; default TLS trust and inherited proxies",
            "duration": "request start through complete response-body read; excludes JSON decoding",
            "order": "health; one warm-up + five sequential reads per endpoint; health",
            "sampleCountPerEndpoint": 5,
            "freshForced": False,
            "cacheFlushed": False,
            "limitation": "Uncontrolled market, network, provider and cache variation; five warm samples establish neither an end-user SLA nor a p95 estimate. This is not a controlled causal before/after test.",
        },
        "healthBefore": check_health(args.expected_sha),
        "endpoints": {},
    }
    if result["healthBefore"]["valid"]:
        for name, path in ENDPOINTS:
            warmup = sample(name, path)
            samples = [sample(name, path) for _ in range(5)]
            result["endpoints"][name] = {
                "warmup": warmup,
                "samples": samples,
                "summary": {
                    "validSamples": sum(item["valid"] for item in samples),
                    "medianDurationMs": statistics.median(item["durationMs"] for item in samples),
                    "statusCounts": {str(status): sum(item.get("status") == status for item in samples) for status in sorted({item.get("status") for item in samples}, key=str)},
                    "sharedCacheHits": [item["metadata"].get("sharedCacheHits") for item in samples],
                    "providerFetches": [item["metadata"].get("providerFetches") for item in samples],
                },
            }
    result["healthAfter"] = check_health(args.expected_sha)
    result["valid"] = (
        result["healthBefore"]["valid"] and result["healthAfter"]["valid"]
        and len(result["endpoints"]) == len(ENDPOINTS)
        and all(endpoint["warmup"]["valid"] and all(item["valid"] for item in endpoint["samples"]) for endpoint in result["endpoints"].values())
    )
    result["completedAt"] = utc_now()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": result["valid"], "expectedSha": args.expected_sha, "output": str(args.output), "endpoints": {name: endpoint["summary"] for name, endpoint in result["endpoints"].items()}}, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
