"""Precompute a fast KOSPI/KOSDAQ technical screener.

Heavy work runs in GitHub Actions after the Korean market closes.
The web app only reads static JSON, so filtering is effectively instant.
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
from pykrx import stock

KST = timezone(timedelta(hours=9))
OUT = Path("static/data/screener.json")
HISTORY_CALENDAR_DAYS = 230
MIN_HISTORY_ROWS = 120


def finite(value, digits=2):
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, digits)
    except (TypeError, ValueError):
        return None


def load_names():
    """Load KOSPI/KOSDAQ names with just two KIND requests."""
    result = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    markets = [("stockMkt", "KOSPI", ".KS"), ("kosdaqMkt", "KOSDAQ", ".KQ")]
    for market_type, market_name, suffix in markets:
        try:
            response = requests.get(
                "https://kind.krx.co.kr/corpgeneral/corpList.do",
                params={"method": "download", "marketType": market_type},
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            frame = pd.read_html(io.StringIO(response.text))[0]
            for _, row in frame.iterrows():
                code = str(row["종목코드"]).zfill(6)
                result[code] = {
                    "name": str(row["회사명"]).strip(),
                    "market": market_name,
                    "symbol": f"{code}{suffix}",
                }
        except Exception as exc:
            print(f"[KIND] {market_name} failed: {exc}")
    return result


def fetch_whole_market(date_str: str):
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            frame = stock.get_market_ohlcv_by_ticker(date_str, market=market)
            if frame is not None and not frame.empty:
                frame = frame.copy()
                frame.index = frame.index.astype(str).str.zfill(6)
                frames.append(frame)
        except Exception as exc:
            print(f"[OHLCV] {date_str} {market}: {exc}")
    return pd.concat(frames, axis=0) if frames else pd.DataFrame()


def fetch_cross_section(date_str: str, getter):
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            frame = getter(date_str, market=market)
            if frame is not None and not frame.empty:
                frame = frame.copy()
                frame.index = frame.index.astype(str).str.zfill(6)
                frames.append(frame)
        except Exception as exc:
            print(f"[XSEC] {date_str} {market}: {exc}")
    return pd.concat(frames, axis=0) if frames else pd.DataFrame()


def calculate_rsi(close: pd.DataFrame):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss.ne(0), 100)
    rsi = rsi.where(avg_gain.ne(0), 0)
    return rsi


def pct_from(close_series: pd.Series, periods: int):
    if len(close_series) <= periods:
        return None
    old = close_series.iloc[-periods - 1]
    new = close_series.iloc[-1]
    if pd.isna(old) or pd.isna(new) or old <= 0:
        return None
    return finite((new / old - 1) * 100, 2)


def build():
    print("Loading Korean stock names...")
    names = load_names()
    today = datetime.now(KST).date()
    business_days = pd.bdate_range(today - timedelta(days=HISTORY_CALENDAR_DAYS), today)

    close_rows = []
    volume_rows = []

    for i, dt in enumerate(business_days):
        date_str = dt.strftime("%Y%m%d")
        frame = fetch_whole_market(date_str)
        if frame.empty or "종가" not in frame.columns:
            continue

        close = pd.to_numeric(frame["종가"], errors="coerce")
        close = close.where(close > 0)
        volume = pd.to_numeric(frame.get("거래량"), errors="coerce").fillna(0)

        close_rows.append(close.rename(date_str))
        volume_rows.append(volume.rename(date_str))
        if i % 20 == 0:
            print(f"Loaded {len(close_rows)} valid trading days; latest={date_str}")
        time.sleep(0.03)

    if len(close_rows) < MIN_HISTORY_ROWS:
        raise RuntimeError(
            f"Only {len(close_rows)} valid trading days loaded; need at least {MIN_HISTORY_ROWS}."
        )

    close = pd.DataFrame(close_rows).sort_index()
    volume = pd.DataFrame(volume_rows).reindex(close.index)
    latest_date = close.index[-1]

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma120 = close.rolling(120).mean()
    vol20 = volume.rolling(20).mean()
    rsi = calculate_rsi(close)

    last = close.iloc[-1]
    prev = close.iloc[-2]
    last_ma20 = ma20.iloc[-1]
    prev_ma20 = ma20.iloc[-2]
    last_ma60 = ma60.iloc[-1]
    last_ma120 = ma120.iloc[-1]
    last_vol = volume.iloc[-1]
    last_vol20 = vol20.iloc[-1]
    last_rsi = rsi.iloc[-1]

    print(f"Loading valuation/cap cross-section for {latest_date}...")
    cap = fetch_cross_section(latest_date, stock.get_market_cap_by_ticker)
    fundamentals = fetch_cross_section(latest_date, stock.get_market_fundamental_by_ticker)

    rows = []
    for code in close.columns:
        price = finite(last.get(code), 0)
        if not price or price <= 0:
            continue

        meta = names.get(code)
        if not meta:
            try:
                fallback_name = stock.get_market_ticker_name(code) or code
            except Exception:
                fallback_name = code
            # Market can only be unknown if KIND missed it.
            meta = {"name": fallback_name, "market": "KRX", "symbol": code}

        m20 = finite(last_ma20.get(code), 0)
        m60 = finite(last_ma60.get(code), 0)
        m120 = finite(last_ma120.get(code), 0)
        rsi14 = finite(last_rsi.get(code), 1)

        avg_vol = last_vol20.get(code)
        volume_ratio = None
        if pd.notna(avg_vol) and avg_vol and avg_vol > 0:
            volume_ratio = finite(last_vol.get(code, 0) / avg_vol, 2)

        prev_price = prev.get(code)
        change1d = None
        if pd.notna(prev_price) and prev_price and prev_price > 0:
            change1d = finite((last.get(code) / prev_price - 1) * 100, 2)

        series = close[code].dropna()
        ret5 = pct_from(series, 5)
        ret20 = pct_from(series, 20)
        ret60 = pct_from(series, 60)

        cross20 = bool(
            pd.notna(prev.get(code))
            and pd.notna(prev_ma20.get(code))
            and pd.notna(last.get(code))
            and pd.notna(last_ma20.get(code))
            and prev.get(code) <= prev_ma20.get(code)
            and last.get(code) > last_ma20.get(code)
        )
        aligned = bool(m20 and m60 and m120 and price > m20 > m60 > m120)
        above20 = bool(m20 and price > m20)
        above60 = bool(m60 and price > m60)

        # Exploratory technical score, not an investment rating.
        score = 0
        if rsi14 is not None and 35 <= rsi14 <= 60:
            score += 20
        if cross20:
            score += 25
        if volume_ratio is not None and volume_ratio >= 1.5:
            score += 20
        elif volume_ratio is not None and volume_ratio >= 1.2:
            score += 10
        if above20:
            score += 15
        if m20 and m60 and m20 > m60:
            score += 10
        if m60 and m120 and m60 > m120:
            score += 10

        market_cap = None
        if not cap.empty and code in cap.index and "시가총액" in cap.columns:
            market_cap = finite(cap.at[code, "시가총액"], 0)

        per = pbr = dividend_yield = None
        if not fundamentals.empty and code in fundamentals.index:
            if "PER" in fundamentals.columns:
                per = finite(fundamentals.at[code, "PER"], 2)
            if "PBR" in fundamentals.columns:
                pbr = finite(fundamentals.at[code, "PBR"], 2)
            if "DIV" in fundamentals.columns:
                dividend_yield = finite(fundamentals.at[code, "DIV"], 2)
            if per == 0:
                per = None
            if pbr == 0:
                pbr = None

        rows.append(
            {
                "code": code,
                "symbol": meta["symbol"],
                "name": meta["name"],
                "market": meta["market"],
                "price": price,
                "change1d": change1d,
                "rsi14": rsi14,
                "volumeRatio": volume_ratio,
                "ma20": m20,
                "ma60": m60,
                "ma120": m120,
                "above20": above20,
                "above60": above60,
                "cross20": cross20,
                "aligned": aligned,
                "ret5": ret5,
                "ret20": ret20,
                "ret60": ret60,
                "marketCap": market_cap,
                "per": per,
                "pbr": pbr,
                "dividendYield": dividend_yield,
                "score": score,
            }
        )

    rows.sort(key=lambda item: (item.get("score") or 0, item.get("marketCap") or 0), reverse=True)
    payload = {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "tradeDate": latest_date,
        "count": len(rows),
        "source": "KRX via pykrx/KIND; precomputed by GitHub Actions",
        "stocks": rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Saved {len(rows)} stocks -> {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    build()
