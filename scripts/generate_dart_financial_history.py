"""Precompute official DART financial statements for the major detail stocks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dart_financial_service import _collect  # noqa: E402

OUT = ROOT / "static/data/dart_financial_history.json"
BUSINESS_CACHE = ROOT / "static/data/dart_business_context.json"
KST = timezone(timedelta(hours=9))


def main():
    if not os.environ.get("DART_API_KEY", "").strip():
        raise RuntimeError("DART_API_KEY is required")
    business = json.loads(BUSINESS_CACHE.read_text(encoding="utf-8"))
    codes = sorted((business.get("companies") or {}).keys())
    if len(codes) < 10:
        raise RuntimeError("Major-company DART universe is incomplete")
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    old_rows = previous.get("companies") or {}
    rows = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(_collect, code, f"{code}.{'KQ' if code == '033500' else 'KS'}"): code for code in codes}
        for future in as_completed(tasks):
            code = tasks[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"{code}: lookup failed: {type(exc).__name__}", flush=True)
                result = None
            if result and result.get("available") and result.get("annual"):
                rows[code] = {k: v for k, v in result.items() if k not in {"checkedAt", "reason"}}
                print(f"{code}: {result.get('annualReportYear')} annual, latest interim {(result.get('interim') or {}).get('quarter')}", flush=True)
            elif isinstance(old_rows.get(code), dict) and old_rows[code].get("available"):
                rows[code] = old_rows[code]
                print(f"{code}: retained last validated financial report", flush=True)
    if len(rows) < 10:
        raise RuntimeError(f"Only {len(rows)} financial histories could be validated")
    if rows == old_rows:
        print("No financial statement changes", flush=True)
        return
    payload = {"generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
               "source": "OpenDART fnlttSinglAcntAll", "companies": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} official financial histories", flush=True)


if __name__ == "__main__":
    main()
