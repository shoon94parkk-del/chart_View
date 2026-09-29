"""Precompute validated DART business-report revenue mixes for major Korean companies.

This removes live DART network latency from common stock-detail views. Only
successful, fail-closed parser results are persisted. Secrets are never stored.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DART_STATIC_CACHE_BYPASS"] = "1"

from dart_business_service import _CACHE, _CACHE_LOCK, fetch_business_report  # noqa: E402

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
    ("042660.KS", "한화오션"),
    ("033500.KQ", "동성화인텍"),
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

    previous_companies = previous.get("companies") if isinstance(previous, dict) else {}
    if not isinstance(previous_companies, dict):
        previous_companies = {}

    companies = {}
    failures = []
    for ticker, name in COMPANIES:
        code = ticker.split(".", 1)[0]
        result = None
        elapsed = 0.0
        for attempt in range(1, 4):
            # A failed live DART request is cached by the service too. Clear
            # only this company before retrying so a transient timeout does
            # not become the result of every retry.
            with _CACHE_LOCK:
                _CACHE.pop(code, None)
            started = time.perf_counter()
            result = fetch_business_report(ticker, name)
            elapsed += time.perf_counter() - started
            if result.get("available") and result.get("sourceMode") in {"opendart-api", "dart-web"}:
                break
            if attempt < 3:
                time.sleep(1.25 * attempt)

        print(
            f"{ticker} {name}: available={result.get('available')} "
            f"basis={result.get('basis')} top={(result.get('topItem') or {}).get('name')} "
            f"attempts<=3 total={elapsed:.2f}s",
            flush=True,
        )

        if result.get("available") and result.get("sourceMode") in {"opendart-api", "dart-web"}:
            companies[code] = stable_row(result, name)
        else:
            previous_row = previous_companies.get(code)
            same_report = bool(
                previous_row
                and result.get("rceptNo")
                and previous_row.get("rceptNo") == result.get("rceptNo")
            )
            report_lookup_failed = not result.get("reportFound")
            can_retain = bool(
                isinstance(previous_row, dict)
                and previous_row.get("available") is True
                and previous_row.get("sourceMode") in {"opendart-api", "dart-web"}
                and (same_report or report_lookup_failed)
            )
            if can_retain:
                companies[code] = previous_row
            failures.append({
                "ticker": ticker,
                "name": name,
                "reason": result.get("reason"),
                "retainedPrevious": can_retain,
            })
        time.sleep(0.25)

    if len(companies) < len(COMPANIES):
        missing = [ticker for ticker, _ in COMPANIES if ticker.split(".", 1)[0] not in companies]
        raise RuntimeError(
            f"validated DART cache incomplete: {len(companies)}/{len(COMPANIES)}; "
            f"missing={missing}; failures={failures}"
        )

    previous_failures = previous.get("failures") if isinstance(previous, dict) else []
    changed = previous_companies != companies or previous_failures != failures
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
