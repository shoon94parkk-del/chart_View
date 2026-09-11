"""Precompute a fast KOSPI/KOSDAQ technical screener.

The expensive whole-market download runs in GitHub Actions after the Korean
market closes. The website only reads the generated JSON, so filtering is
instant and Render does no market-wide work per request.
"""
from __future__ import annotations

import io
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

KST = timezone(timedelta(hours=9))
OUT = Path("static/data/screener.json")
META_OUT = Path("static/data/screener_meta.json")
BATCH_SIZE = 80
PERIOD = "8mo"
MIN_ROWS = 120


def finite(value, digits=2):
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, digits)
    except (TypeError, ValueError):
        return None


def load_universe():
    """Load Korean listed companies from KIND in two bulk requests."""
    stocks = []
    headers = {"User-Agent": "Mozilla/5.0"}
    markets = [("stockMkt", "KOSPI", ".KS"), ("kosdaqMkt", "KOSDAQ", ".KQ")]

    for market_type, market_name, suffix in markets:
        response = requests.get(
            "https://kind.krx.co.kr/corpgeneral/corpList.do",
            params={"method": "download", "marketType": market_type},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        frame = pd.read_html(io.StringIO(response.text))[0]
        for _, row in frame.iterrows():
            code = str(row["종목코드"]).zfill(6)
            stocks.append(
                {
                    "code": code,
                    "name": str(row["회사명"]).strip(),
                    "market": market_name,
                    "symbol": f"{code}{suffix}",
                }
            )

    # Defensive de-duplication while preserving first market assignment.
    seen = set()
    result = []
    for item in stocks:
        if item["symbol"] not in seen:
            seen.add(item["symbol"])
            result.append(item)
    return result


def rsi14(close: pd.Series):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    if len(avg_gain) == 0:
        return None
    g = avg_gain.iloc[-1]
    l = avg_loss.iloc[-1]
    if pd.isna(g) or pd.isna(l):
        return None
    if l == 0:
        return 100.0 if g > 0 else 0.0
    return finite(100 - 100 / (1 + g / l), 1)


def pct_from(close: pd.Series, periods: int):
    if len(close) <= periods:
        return None
    old = close.iloc[-periods - 1]
    new = close.iloc[-1]
    if pd.isna(old) or pd.isna(new) or old <= 0:
        return None
    return finite((new / old - 1) * 100, 2)


def extract_frame(data: pd.DataFrame, symbol: str):
    """Handle both possible yfinance MultiIndex layouts."""
    if data is None or data.empty:
        return None

    if not isinstance(data.columns, pd.MultiIndex):
        return data.copy()

    level0 = data.columns.get_level_values(0)
    level1 = data.columns.get_level_values(1)
    try:
        if symbol in level0:
            return data[symbol].copy()
        if symbol in level1:
            return data.xs(symbol, axis=1, level=1).copy()
    except Exception:
        return None
    return None


def download_batch(symbols):
    """Batch first; retry once in smaller groups when Yahoo drops symbols."""
    return yf.download(
        tickers=symbols,
        period=PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
        timeout=25,
    )


def build_row(meta, frame):
    if frame is None or frame.empty or "Close" not in frame.columns or "Volume" not in frame.columns:
        return None

    close = pd.to_numeric(frame["Close"], errors="coerce")
    volume = pd.to_numeric(frame["Volume"], errors="coerce")
    valid = close.notna() & (close > 0)
    close = close[valid]
    volume = volume.reindex(close.index).fillna(0)

    if len(close) < MIN_ROWS:
        return None

    ma20_series = close.rolling(20).mean()
    ma60_series = close.rolling(60).mean()
    ma120_series = close.rolling(120).mean()

    price = finite(close.iloc[-1], 0)
    previous = finite(close.iloc[-2], 0)
    ma20 = finite(ma20_series.iloc[-1], 0)
    ma60 = finite(ma60_series.iloc[-1], 0)
    ma120 = finite(ma120_series.iloc[-1], 0)
    rsi = rsi14(close)

    volume20 = volume.tail(20).mean()
    volume_ratio = finite(volume.iloc[-1] / volume20, 2) if volume20 and volume20 > 0 else None
    avg_value20 = finite((close.tail(20) * volume.tail(20)).mean(), 0)

    change1d = finite((price / previous - 1) * 100, 2) if price and previous else None
    ret5 = pct_from(close, 5)
    ret20 = pct_from(close, 20)
    ret60 = pct_from(close, 60)

    prev_ma20 = ma20_series.iloc[-2]
    cross20 = bool(
        pd.notna(prev_ma20)
        and close.iloc[-2] <= prev_ma20
        and pd.notna(ma20_series.iloc[-1])
        and close.iloc[-1] > ma20_series.iloc[-1]
    )
    above20 = bool(ma20 and price > ma20)
    above60 = bool(ma60 and price > ma60)
    aligned = bool(ma20 and ma60 and ma120 and price > ma20 > ma60 > ma120)

    # Exploration score only. It intentionally uses technical/liquidity signals
    # that can be computed from one batched price download.
    score = 0
    if rsi is not None and 35 <= rsi <= 60:
        score += 20
    if cross20:
        score += 25
    if volume_ratio is not None and volume_ratio >= 1.5:
        score += 20
    elif volume_ratio is not None and volume_ratio >= 1.2:
        score += 10
    if above20:
        score += 15
    if ma20 and ma60 and ma20 > ma60:
        score += 10
    if ma60 and ma120 and ma60 > ma120:
        score += 10

    latest_date = close.index[-1]
    if hasattr(latest_date, "date"):
        latest_date = latest_date.date().isoformat()
    else:
        latest_date = str(latest_date)[:10]

    return {
        "code": meta["code"],
        "symbol": meta["symbol"],
        "name": meta["name"],
        "market": meta["market"],
        "date": latest_date,
        "price": price,
        "change1d": change1d,
        "rsi14": rsi,
        "volumeRatio": volume_ratio,
        "avgValue20": avg_value20,
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
        "above20": above20,
        "above60": above60,
        "cross20": cross20,
        "aligned": aligned,
        "ret5": ret5,
        "ret20": ret20,
        "ret60": ret60,
        "score": score,
    }


def process_group(group):
    symbols = [item["symbol"] for item in group]
    try:
        data = download_batch(symbols)
    except Exception as exc:
        print(f"Batch failed ({len(symbols)}): {exc}")
        return []

    rows = []
    for meta in group:
        row = build_row(meta, extract_frame(data, meta["symbol"]))
        if row:
            rows.append(row)
    return rows


def build():
    universe = load_universe()
    print(f"Universe: {len(universe)} KOSPI/KOSDAQ companies")

    rows = []
    total_batches = math.ceil(len(universe) / BATCH_SIZE)
    for start in range(0, len(universe), BATCH_SIZE):
        group = universe[start : start + BATCH_SIZE]
        batch_no = start // BATCH_SIZE + 1
        print(f"Downloading batch {batch_no}/{total_batches} ({len(group)} symbols)...")
        batch_rows = process_group(group)

        # If a whole batch is unexpectedly empty, retry it as 20-symbol chunks.
        if not batch_rows:
            print("Batch empty; retrying in smaller groups")
            for small_start in range(0, len(group), 20):
                batch_rows.extend(process_group(group[small_start : small_start + 20]))
                time.sleep(0.4)

        rows.extend(batch_rows)
        time.sleep(0.7)

    if not rows:
        raise RuntimeError("Yahoo batch download returned no usable Korean stocks")

    # Use the freshest market date and drop symbols whose last candle is stale
    # by more than 10 calendar days (long suspensions/delisted remnants).
    freshest = max(row["date"] for row in rows)
    freshest_date = datetime.fromisoformat(freshest).date()
    rows = [
        row
        for row in rows
        if (freshest_date - datetime.fromisoformat(row["date"]).date()).days <= 10
    ]

    rows.sort(key=lambda item: (item.get("score") or 0, item.get("avgValue20") or 0), reverse=True)
    payload = {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "tradeDate": freshest,
        "count": len(rows),
        "universeCount": len(universe),
        "source": "KIND listing + Yahoo Finance batched daily prices; precomputed by GitHub Actions",
        "stocks": rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    meta_payload = {key: payload[key] for key in ("updated", "tradeDate", "count", "universeCount", "source")}
    META_OUT.write_text(json.dumps(meta_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(rows)} stocks -> {OUT} ({OUT.stat().st_size / 1024:.1f} KB); meta -> {META_OUT}")


if __name__ == "__main__":
    build()
