"""Historical PER/PBR band reconstruction from Yahoo public data.

The service intentionally avoids applying today's EPS/BPS to old prices.
It combines split-adjusted historical closes with the TTM diluted EPS and
balance-sheet values that were available around each historical date.
Financial observations are made effective 45 days after period end to reduce
look-ahead bias.
"""
from __future__ import annotations

import bisect
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
CACHE_TTL = 1800
FINANCIAL_LAG_DAYS = 45

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

TYPES = [
    "trailingDilutedEPS", "trailingPeRatio",
    "annualStockholdersEquity", "annualOrdinarySharesNumber",
    "quarterlyStockholdersEquity", "quarterlyOrdinarySharesNumber",
]


def _num(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    r = requests.get(url, params=params, headers=HEADERS, timeout=12)
    r.raise_for_status()
    return r.json()


def _fundamental_series(symbol: str) -> dict[str, list[dict[str, Any]]]:
    url = f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
    payload = _json(url, {
        "symbol": symbol,
        "type": ",".join(TYPES),
        "period1": 0,
        "period2": int(time.time()),
    })
    out: dict[str, list[dict[str, Any]]] = {t: [] for t in TYPES}
    for item in payload.get("timeseries", {}).get("result", []):
        types = item.get("meta", {}).get("type") or []
        if not types:
            continue
        typ = types[0]
        if typ not in out:
            continue
        for row in item.get(typ) or []:
            d = row.get("asOfDate")
            raw = (row.get("reportedValue") or {}).get("raw")
            v = _num(raw)
            if d and v is not None:
                out[typ].append({"date": d, "value": v})
        out[typ].sort(key=lambda x: x["date"])
    return out


def _price_history(symbol: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    payload = _json(url, {
        "range": "5y", "interval": "1d", "events": "splits",
        "includePrePost": "false", "includeAdjustedClose": "true",
    })
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError(f"Yahoo chart returned no data for {symbol}")
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    prices = []
    for ts, close in zip(timestamps, closes):
        v = _num(close)
        if v is None or v <= 0:
            continue
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        prices.append({"date": d, "value": v})

    splits = []
    for event in (result.get("events", {}).get("splits") or {}).values():
        ts = event.get("date")
        numerator = _num(event.get("numerator"))
        denominator = _num(event.get("denominator"))
        if not ts or not numerator or not denominator:
            continue
        ratio = numerator / denominator
        if ratio <= 0:
            continue
        splits.append({
            "date": datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat(),
            "ratio": ratio,
        })
    splits.sort(key=lambda x: x["date"])
    return prices, splits, result.get("meta", {})


def _effective_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        try:
            raw_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        out.append({
            "asOf": raw_date.isoformat(),
            "effective": (raw_date + timedelta(days=FINANCIAL_LAG_DAYS)).isoformat(),
            "value": row["value"],
        })
    out.sort(key=lambda x: x["effective"])
    return out


def _merge_annual_quarterly(series: dict[str, list[dict[str, Any]]], stem: str) -> list[dict[str, Any]]:
    # Annual observations provide the long backfill; quarterly values override
    # equal period ends and add finer recent resolution.
    merged: dict[str, float] = {}
    for prefix in ("annual", "quarterly"):
        for row in series.get(f"{prefix}{stem}", []):
            merged[row["date"]] = row["value"]
    return [{"date": d, "value": merged[d]} for d in sorted(merged)]


def _latest(records: list[dict[str, Any]], dates: list[str], date: str) -> dict[str, Any] | None:
    i = bisect.bisect_right(dates, date) - 1
    return records[i] if i >= 0 else None


def _split_normalized_shares(base: float, as_of: str, splits: list[dict[str, Any]]) -> float:
    """Put historical share counts on Yahoo Chart's split-adjusted price basis."""
    shares = base
    for split in splits:
        if as_of < split["date"]:
            shares *= split["ratio"]
    return shares


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _summarize(points: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    values = [float(x["value"]) for x in points if _num(x.get("value")) is not None]
    if not values:
        return {"metric": metric, "points": [], "stats": None}
    current = values[-1]
    rank = sum(1 for v in values if v <= current) / len(values) * 100
    p20 = _percentile(values, 0.20)
    median = _percentile(values, 0.50)
    p80 = _percentile(values, 0.80)
    mean = sum(values) / len(values)
    if rank <= 20:
        label = "과거 대비 낮은 구간"
    elif rank <= 40:
        label = "과거 평균 이하"
    elif rank < 60:
        label = "과거 중앙권"
    elif rank < 80:
        label = "과거 평균 이상"
    else:
        label = "과거 대비 높은 구간"
    return {
        "metric": metric,
        "points": points,
        "stats": {
            "current": round(current, 3),
            "mean": round(mean, 3),
            "median": round(median, 3) if median is not None else None,
            "p20": round(p20, 3) if p20 is not None else None,
            "p80": round(p80, 3) if p80 is not None else None,
            "percentile": round(rank, 1),
            "label": label,
            "observations": len(values),
            "start": points[0]["time"],
            "end": points[-1]["time"],
        },
    }


def _ratio_check(points: list[dict[str, Any]], sparse_ratio: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compare reconstructed PER with Yahoo's sparse historical ratio snapshots."""
    if not points or not sparse_ratio:
        return None
    point_dates = [x["time"] for x in points]
    diffs = []
    samples = 0
    for ref in sparse_ratio:
        date = ref["date"]
        i = bisect.bisect_right(point_dates, date) - 1
        if i < 0:
            continue
        reconstructed = _num(points[i].get("value"))
        reported = _num(ref.get("value"))
        if not reconstructed or not reported or reported <= 0:
            continue
        diffs.append(abs(reconstructed - reported) / reported * 100)
        samples += 1
    if not diffs:
        return None
    return {"samples": samples, "medianAbsPctDiff": round(_percentile(diffs, 0.5) or 0.0, 1)}


def fetch_valuation_bands(symbol: str, years: int = 3) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    years = max(1, min(int(years or 3), 3))
    key = f"{symbol}|{years}"
    now = time.time()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

    prices, splits, meta = _price_history(symbol)
    fundamentals = _fundamental_series(symbol)
    ttm_eps = _effective_records(fundamentals.get("trailingDilutedEPS", []))
    equity = _effective_records(_merge_annual_quarterly(fundamentals, "StockholdersEquity"))
    shares = _effective_records(_merge_annual_quarterly(fundamentals, "OrdinarySharesNumber"))

    eps_dates = [x["effective"] for x in ttm_eps]
    eq_dates = [x["effective"] for x in equity]
    sh_dates = [x["effective"] for x in shares]
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=366 * years)).isoformat()

    per_daily: list[dict[str, Any]] = []
    pbr_daily: list[dict[str, Any]] = []
    per_candidates = 0
    pbr_candidates = 0
    for row in prices:
        date = row["date"]
        if date < cutoff:
            continue
        price = row["value"]

        eps = _latest(ttm_eps, eps_dates, date)
        if eps and eps["value"] > 0:
            per_candidates += 1
            # Yahoo historical Close is split-adjusted and Yahoo's reported EPS
            # history is restated on the same per-share basis.
            per = price / eps["value"]
            if 0.5 <= per <= 200:
                per_daily.append({"time": date, "value": per})

        sh = _latest(shares, sh_dates, date)
        eq = _latest(equity, eq_dates, date)
        if sh and eq and sh["value"] > 0 and eq["value"] > 0:
            pbr_candidates += 1
            normalized_shares = _split_normalized_shares(sh["value"], sh["asOf"], splits)
            market_cap = price * normalized_shares
            pbr = market_cap / eq["value"]
            if 0.05 <= pbr <= 100:
                pbr_daily.append({"time": date, "value": pbr})

    def weekly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Last trading observation of each ISO week keeps the chart light on mobile.
        bucket: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = datetime.strptime(r["time"], "%Y-%m-%d").date()
            y, w, _ = d.isocalendar()
            bucket[f"{y}-{w:02d}"] = {"time": r["time"], "value": round(float(r["value"]), 3)}
        return [bucket[k] for k in sorted(bucket)]

    per_points = weekly(per_daily)
    pbr_points = weekly(pbr_daily)
    per = _summarize(per_points, "PER")
    pbr = _summarize(pbr_points, "PBR")
    if not per["points"] and not pbr["points"]:
        raise ValueError(f"Historical valuation inputs unavailable for {symbol}")

    validation = _ratio_check(per_points, fundamentals.get("trailingPeRatio", []))
    result = {
        "ticker": symbol,
        "name": meta.get("shortName") or meta.get("longName") or symbol,
        "years": years,
        "per": per,
        "pbr": pbr,
        "source": "Yahoo Finance Chart + Fundamentals Timeseries",
        "method": f"PER=당시 종가/당시 TTM 희석EPS · PBR=당시 시가총액/당시 자본 · 재무값 {FINANCIAL_LAG_DAYS}일 보수적 지연",
        "financialLagDays": FINANCIAL_LAG_DAYS,
        "reconstruction": True,
        "effectiveDateBasis": "period end + 45 days (estimated availability; not the actual filing date)",
        "excluded": {
            "perOutOfRange": max(0, per_candidates - len(per_daily)),
            "pbrOutOfRange": max(0, pbr_candidates - len(pbr_daily)),
            "perAcceptedDaily": len(per_daily),
            "pbrAcceptedDaily": len(pbr_daily),
        },
        "perValidation": validation,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    with _cache_lock:
        _cache[key] = (now, result)
    return result
