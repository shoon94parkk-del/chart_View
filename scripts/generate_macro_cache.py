"""Build a resilient precomputed macro cache for the Render app.

Render never contacts FRED at request time. GitHub Actions refreshes this cache.
The primary source is an open-source FRED proxy because direct cloud-IP access to
fred.stlouisfed.org is currently timing out. Previous good rows are retained as
stale data if an upstream refresh partially fails.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "macro_cache.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/126 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}
FRED_PROXY = "https://fred.libhack.so/v0/observations"

INDICATORS: dict[str, dict[str, str]] = {
    "T10Y2Y": {"name": "장단기 금리차 (10Y-2Y)", "desc": "10년-2년 미국 국채 금리차입니다.", "link": "https://fred.stlouisfed.org/series/T10Y2Y"},
    "T10Y3M": {"name": "장단기 금리차 (10Y-3M)", "desc": "10년-3개월 미국 국채 금리차입니다.", "link": "https://fred.stlouisfed.org/series/T10Y3M"},
    "BAMLH0A0HYM2": {"name": "하이일드 스프레드 (Risk)", "desc": "미국 하이일드 회사채 신용 스프레드입니다.", "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"},
    "RRPONTSYD": {"name": "역래포 잔액 (Liquidity)", "desc": "연준 역레포 시설 잔액입니다.", "link": "https://fred.stlouisfed.org/series/RRPONTSYD"},
    "DFII10": {"name": "10년 실질금리 (TIPS)", "desc": "미국 10년 물가연동국채 실질금리입니다.", "link": "https://fred.stlouisfed.org/series/DFII10"},
    "T10YIE": {"name": "기대인플레이션 (BEI)", "desc": "미국 10년 기대인플레이션입니다.", "link": "https://fred.stlouisfed.org/series/T10YIE"},
    "UNRATE": {"name": "실업률 (Unemployment)", "desc": "미국 실업률입니다.", "link": "https://fred.stlouisfed.org/series/UNRATE"},
    "RSAFS": {"name": "소매판매 (Retail Sales)", "desc": "미국 소매·음식서비스 판매액입니다.", "link": "https://fred.stlouisfed.org/series/RSAFS"},
    "WALCL": {"name": "연준 총자산 (Fed Balance)", "desc": "연준 대차대조표 총자산입니다.", "link": "https://fred.stlouisfed.org/series/WALCL"},
    "WTREGEN": {"name": "재무부 일반계정 (TGA)", "desc": "미 재무부 일반계정 잔액입니다.", "link": "https://fred.stlouisfed.org/series/WTREGEN"},
    "M2SL": {"name": "M2 통화량 (Money Supply)", "desc": "미국 M2 통화량입니다.", "link": "https://fred.stlouisfed.org/series/M2SL"},
    "FEDFUNDS": {"name": "연방기금금리 (Fed Rate)", "desc": "미국 연방기금금리입니다.", "link": "https://fred.stlouisfed.org/series/FEDFUNDS"},
    "^VIX": {"name": "공포 지수 (VIX)", "desc": "미국 주식시장의 기대 변동성입니다.", "link": "https://finance.yahoo.com/quote/%5EVIX"},
}


def get_json(url: str, params: dict[str, Any], attempts: int = 3, timeout: int = 25) -> Any:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(str(last) if last else "request failed")


def normalize_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise RuntimeError("unexpected observations payload")
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "")[:10]
        raw_value = item.get("value")
        if not date or raw_value in (None, ".", ""):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        rows.append({"time": date, "value": round(value, 6)})
    rows.sort(key=lambda x: x["time"])
    return rows[-100:]


def make_row(symbol: str, meta: dict[str, str], rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    if not rows:
        raise RuntimeError(f"no valid observations for {symbol}")
    current = rows[-1]["value"]
    prev = rows[-2]["value"] if len(rows) > 1 else current
    change = ((current - prev) / abs(prev) * 100) if prev else 0.0
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


def fetch_fred(symbol: str, meta: dict[str, str]) -> dict[str, Any]:
    start = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    raw = get_json(
        FRED_PROXY,
        {"series_id": symbol, "observation_start": start},
        attempts=3,
        timeout=25,
    )
    return make_row(symbol, meta, normalize_rows(raw), "FRED via fred.libhack.so cache proxy")


def fetch_vix(meta: dict[str, str]) -> dict[str, Any]:
    period1 = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())
    period2 = int(time.time())
    raw = get_json(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
        {"period1": period1, "period2": period2, "interval": "1d", "events": "history"},
        attempts=2,
        timeout=20,
    )
    result = (raw.get("chart", {}).get("result") or [None])[0] if isinstance(raw, dict) else None
    if not result:
        raise RuntimeError("Yahoo VIX chart missing")
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    rows: list[dict[str, Any]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        value = float(close)
        if value <= 0:
            continue
        rows.append({
            "time": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"),
            "value": round(value, 6),
        })
    return make_row("^VIX", meta, rows[-100:], "Yahoo Chart")


def load_previous() -> dict[str, dict[str, Any]]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
        return {
            str(row.get("original_symbol") or row.get("symbol")): row
            for row in (payload.get("results") or [])
            if isinstance(row, dict)
        }
    except Exception as exc:
        print("previous cache unreadable:", exc)
        return {}


def main() -> None:
    previous = load_previous()
    fresh: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    def fetch_one(symbol: str) -> dict[str, Any]:
        meta = INDICATORS[symbol]
        return fetch_vix(meta) if symbol == "^VIX" else fetch_fred(symbol, meta)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one, symbol): symbol for symbol in INDICATORS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                fresh[symbol] = future.result()
                print("FRESH", symbol, fresh[symbol]["value"], fresh[symbol]["asOf"])
            except Exception as exc:
                errors[symbol] = str(exc)
                print("FAILED", symbol, exc)

    results: dict[str, dict[str, Any]] = dict(fresh)
    stale_symbols: list[str] = []
    for symbol in INDICATORS:
        if symbol in results:
            continue
        old = previous.get(symbol)
        if old:
            kept = dict(old)
            kept["stale"] = True
            kept["staleReason"] = errors.get(symbol, "upstream unavailable")
            results[symbol] = kept
            stale_symbols.append(symbol)
            print("STALE", symbol, kept.get("asOf"))

    ordered = [results[s] for s in INDICATORS if s in results]
    if len(ordered) < 11:
        raise RuntimeError(f"macro cache incomplete: {len(ordered)}/13; errors={errors}")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(ordered),
        "freshCount": len(fresh),
        "staleCount": len(stale_symbols),
        "staleSymbols": stale_symbols,
        "results": ordered,
        "errors": errors,
        "source": "FRED via fred.libhack.so + Yahoo Chart, precomputed by GitHub Actions",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(ordered)} macro series ({len(fresh)} fresh, {len(stale_symbols)} stale) -> {OUT}")


if __name__ == "__main__":
    main()
