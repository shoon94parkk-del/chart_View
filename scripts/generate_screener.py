"""Precompute a fast KOSPI/KOSDAQ technical screener.

Whole-market price work runs in GitHub Actions after the Korean regular close.
This file intentionally scores ONLY the 30-point technical/liquidity layer.
The final recommendation model is 100 points: fundamental/industry 70 + technical 30.
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
    stocks = []
    headers = {"User-Agent": "Mozilla/5.0"}
    markets = [("stockMkt", "KOSPI", ".KS"), ("kosdaqMkt", "KOSDAQ", ".KQ")]
    for market_type, market_name, suffix in markets:
        response = requests.get(
            "https://kind.krx.co.kr/corpgeneral/corpList.do",
            params={"method": "download", "marketType": market_type},
            headers=headers, timeout=30,
        )
        response.raise_for_status()
        frame = pd.read_html(io.StringIO(response.text))[0]
        for _, row in frame.iterrows():
            code = str(row["종목코드"]).zfill(6)
            stocks.append({"code": code, "name": str(row["회사명"]).strip(),
                           "market": market_name, "symbol": f"{code}{suffix}"})
    seen, result = set(), []
    for item in stocks:
        if item["symbol"] not in seen:
            seen.add(item["symbol"]); result.append(item)
    return result


def rsi14(close: pd.Series):
    delta = close.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    if avg_gain.empty: return None
    g, l = avg_gain.iloc[-1], avg_loss.iloc[-1]
    if pd.isna(g) or pd.isna(l): return None
    if l == 0: return 100.0 if g > 0 else 0.0
    return finite(100 - 100/(1 + g/l), 1)


def pct_from(close: pd.Series, periods: int):
    if len(close) <= periods: return None
    old, new = close.iloc[-periods-1], close.iloc[-1]
    if pd.isna(old) or pd.isna(new) or old <= 0: return None
    return finite((new/old - 1)*100, 2)


def extract_frame(data: pd.DataFrame, symbol: str):
    if data is None or data.empty: return None
    if not isinstance(data.columns, pd.MultiIndex): return data.copy()
    level0, level1 = data.columns.get_level_values(0), data.columns.get_level_values(1)
    try:
        if symbol in level0: return data[symbol].copy()
        if symbol in level1: return data.xs(symbol, axis=1, level=1).copy()
    except Exception: return None
    return None


def download_batch(symbols):
    return yf.download(tickers=symbols, period=PERIOD, interval="1d", group_by="ticker",
                       auto_adjust=False, threads=True, progress=False, timeout=25)


def _technical_score(rsi, macd, signal, prev_macd, prev_signal, price, ma20, ma60,
                     bb_mid, bb_upper, volume_ratio, ret5, ret20):
    """30 points exactly: RSI7 + MACD6 + MA/trend6 + Bollinger6 + volume/momentum5."""
    # RSI / 7
    rsi_score = 0
    if rsi is not None:
        if 45 <= rsi <= 65: rsi_score = 7
        elif 40 <= rsi < 45 or 65 < rsi <= 70: rsi_score = 5
        elif 35 <= rsi < 40: rsi_score = 3
        elif rsi > 75: rsi_score = 0
        else: rsi_score = 1

    # MACD / 6
    macd_score = 0
    if None not in (macd, signal):
        if macd > signal and None not in (prev_macd, prev_signal) and prev_macd <= prev_signal: macd_score = 6
        elif macd > signal and macd > 0: macd_score = 5
        elif macd > signal: macd_score = 4
        elif None not in (prev_macd, prev_signal) and (macd-signal) > (prev_macd-prev_signal): macd_score = 2

    # MA/trend / 6
    ma_score = 0
    if None not in (price, ma20, ma60):
        if price > ma20 > ma60: ma_score = 6
        elif price > ma20 and ma20 >= ma60*0.99: ma_score = 5
        elif price > ma20: ma_score = 3
        elif price > ma60: ma_score = 2

    # Bollinger / 6
    bb_score = 0
    if None not in (price, bb_mid, bb_upper) and bb_upper > bb_mid:
        pos = (price-bb_mid)/(bb_upper-bb_mid)
        if 0.10 <= pos <= 0.75: bb_score = 6
        elif 0 <= pos < 0.10: bb_score = 5
        elif 0.75 < pos <= 1.0: bb_score = 4
        elif price >= bb_mid: bb_score = 3
        else: bb_score = 1

    # Volume/momentum / 5
    vm_score = 0
    if volume_ratio is not None:
        if 1.2 <= volume_ratio <= 2.5 and (ret5 or 0) > 0: vm_score = 5
        elif volume_ratio >= 1.0 and (ret5 or 0) > 0: vm_score = 4
        elif (ret20 or 0) > 0: vm_score = 2
    elif (ret20 or 0) > 0: vm_score = 1

    # Chase-risk penalty: technical score should reward entry quality, not vertical spikes.
    penalty = 0
    if rsi is not None and rsi > 75: penalty += 2
    if ret5 is not None and ret5 > 25: penalty += 2
    if ret20 is not None and ret20 > 60: penalty += 2
    total = max(0, min(30, rsi_score + macd_score + ma_score + bb_score + vm_score - penalty))
    return total, {"rsi": rsi_score, "macd": macd_score, "trend": ma_score,
                   "bollinger": bb_score, "volumeMomentum": vm_score, "chasePenalty": penalty}


def build_row(meta, frame):
    if frame is None or frame.empty or "Close" not in frame.columns or "Volume" not in frame.columns: return None
    close = pd.to_numeric(frame["Close"], errors="coerce")
    volume = pd.to_numeric(frame["Volume"], errors="coerce")
    valid = close.notna() & (close > 0); close = close[valid]; volume = volume.reindex(close.index).fillna(0)
    if len(close) < MIN_ROWS: return None

    ma20_s, ma60_s, ma120_s = close.rolling(20).mean(), close.rolling(60).mean(), close.rolling(120).mean()
    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    macd_s = ema12-ema26; signal_s = macd_s.ewm(span=9, adjust=False).mean()
    std20 = close.rolling(20).std(ddof=0); bb_mid_s = ma20_s; bb_upper_s = bb_mid_s + 2*std20; bb_lower_s = bb_mid_s - 2*std20

    price, previous = finite(close.iloc[-1],0), finite(close.iloc[-2],0)
    ma20, ma60, ma120 = finite(ma20_s.iloc[-1],0), finite(ma60_s.iloc[-1],0), finite(ma120_s.iloc[-1],0)
    rsi = rsi14(close)
    macd, signal = finite(macd_s.iloc[-1],2), finite(signal_s.iloc[-1],2)
    prev_macd, prev_signal = finite(macd_s.iloc[-2],2), finite(signal_s.iloc[-2],2)
    bb_mid, bb_upper, bb_lower = finite(bb_mid_s.iloc[-1],0), finite(bb_upper_s.iloc[-1],0), finite(bb_lower_s.iloc[-1],0)

    volume20 = volume.tail(20).mean(); volume_ratio = finite(volume.iloc[-1]/volume20,2) if volume20 and volume20>0 else None
    avg_value20 = finite((close.tail(20)*volume.tail(20)).mean(),0)
    change1d = finite((price/previous-1)*100,2) if price and previous else None
    ret5, ret20, ret60 = pct_from(close,5), pct_from(close,20), pct_from(close,60)

    prev_ma20 = ma20_s.iloc[-2]
    cross20 = bool(pd.notna(prev_ma20) and close.iloc[-2] <= prev_ma20 and pd.notna(ma20_s.iloc[-1]) and close.iloc[-1] > ma20_s.iloc[-1])
    above20, above60 = bool(ma20 and price > ma20), bool(ma60 and price > ma60)
    aligned = bool(ma20 and ma60 and ma120 and price > ma20 > ma60 > ma120)
    technical_score, breakdown = _technical_score(rsi,macd,signal,prev_macd,prev_signal,price,ma20,ma60,bb_mid,bb_upper,volume_ratio,ret5,ret20)

    latest_date = close.index[-1]
    latest_date = latest_date.date().isoformat() if hasattr(latest_date,"date") else str(latest_date)[:10]
    return {"code":meta["code"],"symbol":meta["symbol"],"name":meta["name"],"market":meta["market"],"date":latest_date,
            "price":price,"previousClose":previous,"change1d":change1d,"rsi14":rsi,"macd":macd,"macdSignal":signal,
            "volumeRatio":volume_ratio,"avgValue20":avg_value20,"ma20":ma20,"ma60":ma60,"ma120":ma120,
            "bbMid":bb_mid,"bbUpper":bb_upper,"bbLower":bb_lower,"above20":above20,"above60":above60,"cross20":cross20,
            "aligned":aligned,"ret5":ret5,"ret20":ret20,"ret60":ret60,
            "technicalScore":technical_score,"technicalBreakdown":breakdown,"score":technical_score}


def process_group(group):
    symbols=[item["symbol"] for item in group]
    try: data=download_batch(symbols)
    except Exception as exc:
        print(f"Batch failed ({len(symbols)}): {exc}"); return []
    rows=[]
    for meta in group:
        row=build_row(meta,extract_frame(data,meta["symbol"]))
        if row: rows.append(row)
    return rows


def build():
    universe=load_universe(); print(f"Universe: {len(universe)} KOSPI/KOSDAQ companies")
    rows=[]; total_batches=math.ceil(len(universe)/BATCH_SIZE)
    for start in range(0,len(universe),BATCH_SIZE):
        group=universe[start:start+BATCH_SIZE]; batch_no=start//BATCH_SIZE+1
        print(f"Downloading batch {batch_no}/{total_batches} ({len(group)} symbols)...")
        batch_rows=process_group(group)
        if not batch_rows:
            print("Batch empty; retrying in smaller groups")
            for small_start in range(0,len(group),20):
                batch_rows.extend(process_group(group[small_start:small_start+20])); time.sleep(0.4)
        rows.extend(batch_rows); time.sleep(0.7)
    if not rows: raise RuntimeError("Yahoo batch download returned no usable Korean stocks")

    freshest=max(row["date"] for row in rows); freshest_date=datetime.fromisoformat(freshest).date()
    rows=[row for row in rows if (freshest_date-datetime.fromisoformat(row["date"]).date()).days <= 10]
    rows.sort(key=lambda item:(item.get("technicalScore") or 0,item.get("avgValue20") or 0),reverse=True)
    payload={"updated":datetime.now(KST).isoformat(timespec="seconds"),"tradeDate":freshest,"count":len(rows),
             "universeCount":len(universe),"scoreModel":"technical 30 only; final recommendation = fundamental/industry 70 + technical 30",
             "source":"KIND listing + Yahoo Finance batched daily prices; precomputed by GitHub Actions","stocks":rows}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    meta_payload={key:payload[key] for key in ("updated","tradeDate","count","universeCount","scoreModel","source")}
    META_OUT.write_text(json.dumps(meta_payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"Saved {len(rows)} stocks -> {OUT} ({OUT.stat().st_size/1024:.1f} KB); meta -> {META_OUT}")

if __name__ == "__main__": build()
