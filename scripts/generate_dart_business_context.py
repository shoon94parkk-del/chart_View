"""Precompute validated DART business-report revenue mixes for major Korean companies.

This removes live DART network latency from common stock-detail views. Only
successful, fail-closed parser results are persisted. Secrets are never stored.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

os.environ["DART_STATIC_CACHE_BYPASS"] = "1"

from dart_business_service import fetch_business_report  # noqa: E402

KST = timezone(timedelta(hours=9))
OUT = Path("static/data/dart_business_context.json")

COMPANIES = [
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    ("373220.KS", "LG에너지솔루션"),
    ("207940.KS", "삼성바이오로직스"),
    ("005380.KS", "현대차"),
    ("000270.KS", "기아"),
    ("006400.KS", "삼성SDI"),
    ("066570.KS", "LG전자"),
    ("035420.KS", "NAVER"),
    ("035720.KS", "카카오"),
    ("068270.KS", "셀트리온"),
    ("005490.KS", "POSCO홀딩스"),
]

VOLATILE_KEYS = {"checkedAt", "cache", "cacheMode"}


def stable_row(result: dict, name: str) -> dict:
    row = {k: v for k, v in result.items() if k not in VOLATILE_KEYS}
    row["name"] = name
    return row


def main() -> None:
    if not os.environ.get("DART_API_KEY", "").strip():
        raise RuntimeError("DART_API_KEY is required")

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    companies = {}
    failures = []
    for ticker, name in COMPANIES:
        code = ticker.split(".", 1)[0]
        started = time.perf_counter()
        result = fetch_business_report(ticker, name)
        elapsed = time.perf_counter() - started
        print(
            f"{ticker} {name}: available={result.get('available')} "
            f"basis={result.get('basis')} top={(result.get('topItem') or {}).get('name')} "
            f"{elapsed:.2f}s",
            flush=True,
        )
        if result.get("available") and result.get("sourceMode") == "opendart-api":
            companies[code] = stable_row(result, name)
        else:
            failures.append({"ticker": ticker, "name": name, "reason": result.get("reason")})
        time.sleep(0.25)

    if len(companies) < 10:
        raise RuntimeError(f"too few validated DART rows: {len(companies)}; failures={failures}")

    previous_companies = previous.get("companies") if isinstance(previous, dict) else {}
    changed = previous_companies != companies
    if not changed and OUT.exists():
        print("No validated DART business-context changes")
        return

    payload = {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "OpenDART + DART viewer, fail-closed parser",
        "count": len(companies),
        "companies": companies,
        "failures": failures,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(companies)} validated DART business contexts; failures={len(failures)}")


if __name__ == "__main__":
    main()
