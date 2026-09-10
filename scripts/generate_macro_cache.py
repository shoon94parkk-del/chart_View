"""Build a resilient precomputed macro cache for the Render app.

The web server never contacts FRED at request time. GitHub Actions refreshes a
committed JSON cache every six hours. Most FRED series are mirrored as CSV by
Equibles; the two missing feeds (DFII10 and WTREGEN) come from DBnomics mirrors
of Federal Reserve datasets. Previous valid rows are retained as stale data if
a later refresh partially fails.
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "macro_cache.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "text/csv,application/json,text/plain,*/*",
}

INDICATORS: dict[str, dict[str, str]] = {
    "T10Y2Y": {"name": "장단기 금리차 (10Y-2Y)", "desc": "10년-2년 미국 국채 금리차입니다.", "link": "https://fred.stlouisfed.org/series/T10Y2Y", "feed": "equibles:t10y2y"},
    "T10Y3M": {"name": "장단기 금리차 (10Y-3M)", "desc": "10년-3개월 미국 국채 금리차입니다.", "link": "https://fred.stlouisfed.org/series/T10Y3M", "feed": "equibles:t10y3m"},
    "BAMLH0A0HYM2": {"name": "하이일드 스프레드 (Risk)", "desc": "미국 하이일드 회사채 옵션조정 스프레드입니다.", "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "feed": "equibles:bamlh0a0hym2"},
    "RRPONTSYD": {"name": "역래포 잔액 (Liquidity)", "desc": "연준 역레포 시설 잔액입니다.", "link": "https://fred.stlouisfed.org/series/RRPONTSYD", "feed": "equibles:rrpontsyd"},
    "DFII10": {"name": "10년 실질금리 (TIPS)", "desc": "미국 10년 물가연동국채 실질금리입니다.", "link": "https://fred.stlouisfed.org/series/DFII10", "feed": "dbnomics:FED/H15/RIFLGFCY10_XII_N.B"},
    "T10YIE": {"name": "기대인플레이션 (BEI)", "desc": "미국 10년 기대인플레이션입니다.", "link": "https://fred.stlouisfed.org/series/T10YIE", "feed": "equibles:t10yie"},
    "UNRATE": {"name": "실업률 (Unemployment)", "desc": "미국 실업률입니다.", "link": "https://fred.stlouisfed.org/series/UNRATE", "feed": "equibles:unrate"},
    "RSAFS": {"name": "소매판매 (Retail Sales)", "desc": "미국 소매·음식서비스 판매액입니다.", "link": "https://fred.stlouisfed.org/series/RSAFS", "feed": "equibles:rsafs"},
    "WALCL": {"name": "연준 총자산 (Fed Balance)", "desc": "연준 대차대조표 총자산입니다.", "link": "https://fred.stlouisfed.org/series/WALCL", "feed": "equibles:walcl"},
    "WTREGEN": {"name": "재무부 일반계정 (TGA)", "desc": "미 재무부 일반계정 잔액입니다.", "link": "https://fred.stlouisfed.org/series/WTREGEN", "feed": "dbnomics:FED/H41/RESPPLLDT_N.WW"},
    "M2SL": {"name": "M2 통화량 (Money Supply)", "desc": "미국 M2 통화량입니다.", "link": "https://fred.stlouisfed.org/series/M2SL", "feed": "equibles:m2sl"},
    "FEDFUNDS": {"name": "연방기금금리 (Fed Rate)", "desc": "미국 연방기금금리입니다.", "link": "https://fred.stlouisfed.org/series/FEDFUNDS", "feed": "equibles:fedfunds"},
    "^VIX": {"name": "공포 지수 (VIX)", "desc": "CBOE VIX 종가 시계열입니다.", "link": "https://fred.stlouisfed.org/series/VIXCLS", "feed": "equibles:vixcls"},
}


def _get(url: str, *, want_json: bool = False, attempts: int = 3, timeout: int = 30) -> Any:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response.json() if want_json else response.text
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(str(last) if last else "request failed")


def _finite_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if text.upper() in {"", ".", "NA", "N/A", "NAN", "NONE"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_equibles(slug: str) -> list[dict[str, Any]]:
    text = _get(f"https://equibles.com/economicdata/{slug}.csv")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows: list[dict[str, Any]] = []
    for item in reader:
        date = str(item.get("Date") or "").strip()[:10]
        value = _finite_number(item.get("Value"))
        if not date or value is None:
            continue
        rows.append({"time": date, "value": round(value, 6)})
    rows.sort(key=lambda x: x["time"])
    if not rows:
        raise RuntimeError(f"Equibles returned no observations for {slug}")
    return rows[-100:]


def fetch_dbnomics(path: str) -> list[dict[str, Any]]:
    payload = _get(
        f"https://api.db.nomics.world/v22/series/{path}?observations=1",
        want_json=True,
    )
    docs = ((payload.get("series") or {}).get("docs") or []) if isinstance(payload, dict) else []
    if not docs:
        raise RuntimeError(f"DBnomics returned no series for {path}")
    doc = docs[0]
    periods = doc.get("period") or []
    values = doc.get("value") or []
    rows: list[dict[str, Any]] = []
    for period, raw_value in zip(periods, values):
        value = _finite_number(raw_value)
        date = str(period or "").strip()[:10]
        if not date or value is None:
            continue
        rows.append({"time": date, "value": round(value, 6)})
    rows.sort(key=lambda x: x["time"])
    if not rows:
        raise RuntimeError(f"DBnomics returned no observations for {path}")
    return rows[-100:]


def make_row(symbol: str, meta: dict[str, str], rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    current = rows[-1]["value"]
    previous = rows[-2]["value"] if len(rows) > 1 else current
    change = ((current - previous) / abs(previous) * 100) if previous else 0.0
    return {
        "original_symbol": symbol,
        "symbol": symbol,
        "name": meta["name"],
        "desc": meta["desc"],
        "link": meta["link"],
        "value": round(current, 4),
        "change": round(change, 2),
        "chart_data": rows,
        "source": source,
        "asOf": rows[-1]["time"],
        "stale": False,
    }


def fetch_one(symbol: str) -> dict[str, Any]:
    meta = INDICATORS[symbol]
    kind, target = meta["feed"].split(":", 1)
    if kind == "equibles":
        rows = fetch_equibles(target)
        source = "FRED mirror · Equibles CSV"
    elif kind == "dbnomics":
        rows = fetch_dbnomics(target)
        source = "Federal Reserve mirror · DBnomics"
    else:
        raise RuntimeError(f"unknown feed type: {kind}")
    return make_row(symbol, meta, rows, source)


def load_previous() -> dict[str, dict[str, Any]]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
        return {
            str(row.get("original_symbol") or row.get("symbol")): row
            for row in (payload.get("results") or [])
            if isinstance(row, dict) and row.get("chart_data")
        }
    except Exception as exc:
        print("previous cache unreadable:", exc)
        return {}


def main() -> None:
    previous = load_previous()
    fresh: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    # The feeds are public and light enough for modest parallelism. Keeping the
    # pool small reduces rate-limit risk while completing well inside Actions' limit.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one, symbol): symbol for symbol in INDICATORS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                row = future.result()
                fresh[symbol] = row
                print("FRESH", symbol, row["value"], row["asOf"], row["source"])
            except Exception as exc:
                errors[symbol] = str(exc)
                print("FAILED", symbol, exc)

    results: dict[str, dict[str, Any]] = dict(fresh)
    stale_symbols: list[str] = []
    for symbol in INDICATORS:
        if symbol in results:
            continue
        old = previous.get(symbol)
        if not old:
            continue
        kept = dict(old)
        kept["stale"] = True
        kept["staleReason"] = errors.get(symbol, "upstream unavailable")
        results[symbol] = kept
        stale_symbols.append(symbol)
        print("STALE", symbol, kept.get("asOf"))

    ordered = [results[symbol] for symbol in INDICATORS if symbol in results]

    # Never create a partial first cache. After a successful baseline exists,
    # tolerate up to two temporarily unavailable feeds by keeping stale rows.
    required = len(INDICATORS) if not previous else 11
    if len(ordered) < required:
        raise RuntimeError(
            f"macro cache incomplete: {len(ordered)}/{len(INDICATORS)}; errors={errors}"
        )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(ordered),
        "freshCount": len(fresh),
        "staleCount": len(stale_symbols),
        "staleSymbols": stale_symbols,
        "results": ordered,
        "errors": errors,
        "source": "FRED/Federal Reserve data precomputed by GitHub Actions via Equibles + DBnomics mirrors",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"wrote {len(ordered)} macro series "
        f"({len(fresh)} fresh, {len(stale_symbols)} stale) -> {OUT}"
    )


if __name__ == "__main__":
    main()
