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
from bs4 import BeautifulSoup

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
    "PCEPI": {"name": "PCE 물가 (YoY)", "desc": "미국 개인소비지출(PCE) 물가지수의 전년동월비입니다. 연준이 중시하는 광범위한 소비물가 흐름을 보여줍니다.", "link": "https://fred.stlouisfed.org/series/PCEPI", "feed": "dallaspce:pce"},
    "PCETRIM12M159SFRBDAL": {"name": "절사평균 PCE (YoY)", "desc": "Dallas Fed가 극단적인 가격변동 항목을 양쪽에서 절사한 뒤 계산한 PCE 기반 핵심물가의 12개월 변화율입니다.", "link": "https://fred.stlouisfed.org/series/PCETRIM12M159SFRBDAL", "feed": "dallaspce:trimmed"},
    "UNRATE": {"name": "실업률 (Unemployment)", "desc": "미국 실업률입니다.", "link": "https://fred.stlouisfed.org/series/UNRATE", "feed": "equibles:unrate"},
    "RSAFS": {"name": "소매판매 (Retail Sales)", "desc": "미국 소매·음식서비스 판매액입니다.", "link": "https://fred.stlouisfed.org/series/RSAFS", "feed": "equibles:rsafs"},
    "WALCL": {"name": "연준 총자산 (Fed Balance)", "desc": "연준 대차대조표 총자산입니다.", "link": "https://fred.stlouisfed.org/series/WALCL", "feed": "equibles:walcl"},
    "WTREGEN": {"name": "재무부 일반계정 (TGA)", "desc": "미 재무부 일반계정 잔액입니다.", "link": "https://fred.stlouisfed.org/series/WTREGEN", "feed": "dbnomics:FED/H41/RESPPLLDT_N.WW"},
    "M2SL": {"name": "M2 통화량 (Money Supply)", "desc": "미국 M2 통화량입니다.", "link": "https://fred.stlouisfed.org/series/M2SL", "feed": "equibles:m2sl"},
    "FEDTARGET": {"name": "연준 목표금리 범위", "desc": "FOMC가 정한 연방기금금리 목표 범위입니다. 정책 결정이 반영되면 일 단위로 갱신됩니다.", "link": "https://fred.stlouisfed.org/series/DFEDTARU", "feed": "policy:fedtarget"},
    "DFF": {"name": "실효 연방기금금리 (EFFR)", "desc": "미국 은행간 실제 익일 연방기금 거래를 바탕으로 한 실효금리입니다.", "link": "https://fred.stlouisfed.org/series/DFF", "feed": "equibles:dff"},
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


def fetch_fred_csv(series_id: str) -> list[dict[str, Any]]:
    text = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows: list[dict[str, Any]] = []
    for item in reader:
        date = str(item.get("DATE") or item.get("observation_date") or "").strip()[:10]
        value = _finite_number(item.get(series_id) if series_id in item else item.get("VALUE"))
        if not date or value is None:
            continue
        rows.append({"time": date, "value": round(value, 6)})
    rows.sort(key=lambda x: x["time"])
    if not rows:
        raise RuntimeError(f"FRED CSV returned no observations for {series_id}")
    return rows[-120:]


def transform_yoy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) < 13:
        raise RuntimeError("not enough monthly observations for YoY transform")
    output: list[dict[str, Any]] = []
    for index in range(12, len(rows)):
        current = _finite_number(rows[index].get("value"))
        previous = _finite_number(rows[index - 12].get("value"))
        if current is None or previous in (None, 0):
            continue
        yoy = ((current / previous) - 1.0) * 100.0
        output.append({"time": rows[index]["time"], "value": round(yoy, 6)})
    if not output:
        raise RuntimeError("YoY transform produced no observations")
    return output[-100:]


def fetch_dallas_pce(kind: str) -> list[dict[str, Any]]:
    html = _get("https://www.dallasfed.org/research/pce", attempts=3, timeout=30)
    soup = BeautifulSoup(html, "html.parser")
    heading = None
    for tag in soup.find_all(["h3", "h4"]):
        if "12-month PCE inflation" in tag.get_text(" ", strip=True):
            heading = tag
            break
    table = heading.find_next("table") if heading else None
    if table is None:
        raise RuntimeError("Dallas Fed 12-month PCE table not found")
    rows = table.find_all("tr")
    if len(rows) < 2:
        raise RuntimeError("Dallas Fed PCE table has no data rows")
    header = [cell.get_text(" ", strip=True) for cell in rows[0].find_all(["th", "td"])]
    dates = header[1:]
    target = None
    for row in rows[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if not cells:
            continue
        label = cells[0].strip().lower()
        if kind == "pce" and label == "pce":
            target = cells[1:]
            break
        if kind == "trimmed" and label.startswith("trimmed mean"):
            target = cells[1:]
            break
    if target is None:
        raise RuntimeError(f"Dallas Fed PCE row not found: {kind}")
    output: list[dict[str, Any]] = []
    for raw_date, raw_value in zip(dates, target):
        value = _finite_number(raw_value)
        if value is None:
            continue
        try:
            date = datetime.strptime(raw_date.strip(), "%y-%b").strftime("%Y-%m-01")
        except ValueError:
            continue
        output.append({"time": date, "value": round(value, 6)})
    if not output:
        raise RuntimeError(f"Dallas Fed PCE row empty: {kind}")
    output.sort(key=lambda x: x["time"])
    return output


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


def fetch_policy_target() -> dict[str, Any]:
    """Build one visible policy-rate row from the official daily target bounds."""
    lower_rows = fetch_equibles("dfed tarl".replace(" ", ""))
    upper_rows = fetch_equibles("dfedtaru")
    lower_map = {row["time"]: row["value"] for row in lower_rows}
    upper_map = {row["time"]: row["value"] for row in upper_rows}
    common_dates = sorted(set(lower_map) & set(upper_map))
    if not common_dates:
        raise RuntimeError("target-rate bounds have no overlapping observations")

    chart_rows: list[dict[str, Any]] = []
    for date in common_dates:
        lower = float(lower_map[date])
        upper = float(upper_map[date])
        chart_rows.append({
            "time": date,
            "value": round((lower + upper) / 2.0, 6),
            "lower": round(lower, 6),
            "upper": round(upper, 6),
        })

    latest = chart_rows[-1]
    previous_distinct = latest
    for row in reversed(chart_rows[:-1]):
        if row["lower"] != latest["lower"] or row["upper"] != latest["upper"]:
            previous_distinct = row
            break

    move_bp = round((latest["value"] - previous_distinct["value"]) * 100.0, 2)
    return {
        "original_symbol": "FEDTARGET",
        "symbol": "FEDTARGET",
        "name": INDICATORS["FEDTARGET"]["name"],
        "desc": INDICATORS["FEDTARGET"]["desc"],
        "link": INDICATORS["FEDTARGET"]["link"],
        "value": round(latest["value"], 4),
        "delta": round(latest["value"] - previous_distinct["value"], 4),
        "change": 0.0,
        "moveBp": move_bp,
        "targetLower": latest["lower"],
        "targetUpper": latest["upper"],
        "previousTargetLower": previous_distinct["lower"],
        "previousTargetUpper": previous_distinct["upper"],
        "chart_data": chart_rows[-120:],
        "source": "Federal Reserve / FRED mirror · Equibles daily target range",
        "asOf": latest["time"],
        "stale": False,
    }


def make_row(symbol: str, meta: dict[str, str], rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    current = rows[-1]["value"]
    previous = rows[-2]["value"] if len(rows) > 1 else current
    delta = current - previous
    change = ((delta / abs(previous)) * 100) if previous else 0.0
    return {
        "original_symbol": symbol,
        "symbol": symbol,
        "name": meta["name"],
        "desc": meta["desc"],
        "link": meta["link"],
        "value": round(current, 4),
        "delta": round(delta, 4),
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
    elif kind == "fredcsv":
        rows = fetch_fred_csv(target)
        source = "FRED CSV"
    elif kind == "policy":
        return fetch_policy_target()
    elif kind == "dallaspce":
        rows = fetch_dallas_pce(target)
        source = "Federal Reserve Bank of Dallas · PCE"
    elif kind == "dbnomics":
        rows = fetch_dbnomics(target)
        source = "Federal Reserve mirror · DBnomics"
    else:
        raise RuntimeError(f"unknown feed type: {kind}")
    if meta.get("transform") == "yoy":
        rows = transform_yoy(rows)
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
    required = len(INDICATORS) if not previous else 13
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
        "source": "FRED/Federal Reserve data precomputed by GitHub Actions via FRED CSV + Equibles + DBnomics",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"wrote {len(ordered)} macro series "
        f"({len(fresh)} fresh, {len(stale_symbols)} stale) -> {OUT}"
    )


if __name__ == "__main__":
    main()
