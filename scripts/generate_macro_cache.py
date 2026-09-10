"""Generate a resilient macro-data cache for the Render app.

FRED is fetched from GitHub Actions rather than from Render shared IPs, which can
be slow or blocked. The web app serves the committed JSON without runtime calls.
If one upstream series temporarily fails, the previous cached value is retained
and explicitly marked stale instead of breaking the whole macro dashboard.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "macro_cache.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "text/csv,application/json,text/plain,*/*"}

INDICATORS: dict[str, dict[str, str]] = {
    "T10Y2Y": {"name": "장단기 금리차 (10Y-2Y)", "desc": "경기 침체 신호등. 0 이하(역전)로 내려갔다가 다시 올라올 때 침체가 시작되는 경향이 있습니다.", "link": "https://fred.stlouisfed.org/series/T10Y2Y", "source": "FRED"},
    "T10Y3M": {"name": "장단기 금리차 (10Y-3M)", "desc": "연준이 중요하게 보는 침체 지표 중 하나입니다.", "link": "https://fred.stlouisfed.org/series/T10Y3M", "source": "FRED"},
    "BAMLH0A0HYM2": {"name": "하이일드 스프레드 (Risk)", "desc": "기업 신용 위험을 보여주는 지표입니다.", "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "source": "FRED"},
    "RRPONTSYD": {"name": "역래포 잔액 (Liquidity)", "desc": "연준 역레포 시설에 머무는 유동성 규모입니다.", "link": "https://fred.stlouisfed.org/series/RRPONTSYD", "source": "FRED"},
    "DFII10": {"name": "10년 실질금리 (TIPS)", "desc": "인플레이션 기대를 제외한 미국 10년 실질금리입니다.", "link": "https://fred.stlouisfed.org/series/DFII10", "source": "FRED"},
    "T10YIE": {"name": "기대인플레이션 (BEI)", "desc": "미국 10년 기대인플레이션 지표입니다.", "link": "https://fred.stlouisfed.org/series/T10YIE", "source": "FRED"},
    "UNRATE": {"name": "실업률 (Unemployment)", "desc": "미국 실업률입니다.", "link": "https://fred.stlouisfed.org/series/UNRATE", "source": "FRED"},
    "RSAFS": {"name": "소매판매 (Retail Sales)", "desc": "미국 소매·음식서비스 판매액입니다.", "link": "https://fred.stlouisfed.org/series/RSAFS", "source": "FRED"},
    "WALCL": {"name": "연준 총자산 (Fed Balance)", "desc": "연준 대차대조표 총자산입니다.", "link": "https://fred.stlouisfed.org/series/WALCL", "source": "FRED"},
    "WTREGEN": {"name": "재무부 일반계정 (TGA)", "desc": "미 재무부의 연준 예치금 규모입니다.", "link": "https://fred.stlouisfed.org/series/WTREGEN", "source": "FRED"},
    "M2SL": {"name": "M2 통화량 (Money Supply)", "desc": "미국 M2 통화량입니다.", "link": "https://fred.stlouisfed.org/series/M2SL", "source": "FRED"},
    "FEDFUNDS": {"name": "연방기금금리 (Fed Rate)", "desc": "미국 연방기금금리 월간 시계열입니다.", "link": "https://fred.stlouisfed.org/series/FEDFUNDS", "source": "FRED"},
    "^VIX": {"name": "공포 지수 (VIX)", "desc": "미국 주식시장의 기대 변동성을 나타냅니다.", "link": "https://finance.yahoo.com/quote/%5EVIX", "source": "YAHOO"},
}


def request_with_retry(url: str, *, params: dict[str, Any], attempts: int = 3) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=25)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError(str(last_error) if last_error else "request failed")


def fetch_fred(symbol: str, meta: dict[str, str]) -> dict[str, Any]:
    start = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    response = request_with_retry(
        "https://fred.stlouisfed.org/graph/fredgraph.csv",
        params={"id": symbol, "cosd": start},
    )
    frame = pd.read_csv(StringIO(response.text))
    if frame.empty or len(frame.columns) < 2:
        raise RuntimeError(f"empty FRED series {symbol}")

    date_col = frame.columns[0]
    value_col = symbol if symbol in frame.columns else frame.columns[-1]
    values = pd.to_numeric(frame[value_col], errors="coerce")
    rows = [
        {"time": str(date)[:10], "value": round(float(value), 6)}
        for date, value in zip(frame[date_col], values)
        if pd.notna(value)
    ][-100:]
    if not rows:
        raise RuntimeError(f"no valid FRED values {symbol}")

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
        "source": "FRED",
        "asOf": rows[-1]["time"],
        "stale": False,
    }


def fetch_vix(meta: dict[str, str]) -> dict[str, Any]:
    period1 = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())
    period2 = int(time.time())
    response = request_with_retry(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
        params={"period1": period1, "period2": period2, "interval": "1d", "events": "history"},
    )
    result = (response.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("Yahoo VIX chart missing")

    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        value = float(close)
        if value <= 0:
            continue
        rows.append({"time": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"), "value": round(value, 4)})
    rows = rows[-100:]
    if not rows:
        raise RuntimeError("Yahoo VIX values missing")

    current = rows[-1]["value"]
    prev = rows[-2]["value"] if len(rows) > 1 else current
    return {
        "original_symbol": "^VIX",
        "symbol": "^VIX",
        "name": meta["name"],
        "desc": meta["desc"],
        "link": meta["link"],
        "value": round(current, 2),
        "change": round((current - prev) / prev * 100 if prev else 0.0, 2),
        "chart_data": rows,
        "source": "Yahoo Chart",
        "asOf": rows[-1]["time"],
        "stale": False,
    }


def load_previous() -> dict[str, dict[str, Any]]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
        rows = payload.get("results") or []
        return {
            str(row.get("original_symbol") or row.get("symbol")): row
            for row in rows
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
        if not old:
            continue
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
        "source": "FRED + Yahoo Chart, precomputed by GitHub Actions",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(ordered)} macro series ({len(fresh)} fresh, {len(stale_symbols)} stale) -> {OUT}")


if __name__ == "__main__":
    main()
