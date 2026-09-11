from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote as urlquote

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consensus_service import fetch_live_consensus

DATA = ROOT / "static" / "data"
VALUATION_CACHE = DATA / "valuation_cache.json"
OUT_CACHE = DATA / "consensus_cache.json"
OUT_HISTORY = DATA / "consensus_history.json"
MAX_HISTORY_DAYS = 180
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def selected_symbols() -> list[str]:
    payload = load_json(VALUATION_CACHE)
    quotes = payload.get("quotes") or {}
    symbols = [str(x).upper() for x in quotes.keys() if x]
    for symbol in ("AAPL", "NVDA", "005930.KS", "000660.KS"):
        if symbol not in symbols:
            symbols.append(symbol)
    return sorted(set(symbols))


def _finite(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def fetch_price_trend(symbol: str) -> dict:
    """Fetch adjusted-close returns matching the 30/90-day EPS revision windows."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urlquote(symbol, safe='')}"
    response = requests.get(
        url,
        headers=HEADERS,
        params={
            "range": "6mo",
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        },
        timeout=12,
    )
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError(f"Yahoo chart returned no result for {symbol}")

    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    adj_rows = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
    close_rows = (indicators.get("quote") or [{}])[0].get("close") or []
    values = adj_rows if len(adj_rows) == len(timestamps) else close_rows

    pairs: list[tuple[datetime, float]] = []
    for stamp, raw in zip(timestamps, values):
        value = _finite(raw)
        if value is None or value <= 0:
            continue
        pairs.append((datetime.fromtimestamp(int(stamp), tz=timezone.utc), value))
    if len(pairs) < 20:
        raise ValueError(f"insufficient price history for {symbol}")
    pairs.sort(key=lambda item: item[0])

    latest_dt, current = pairs[-1]

    def point_before(days: int) -> tuple[str | None, float | None]:
        target = latest_dt - timedelta(days=days)
        eligible = [(dt, value) for dt, value in pairs if dt <= target]
        if not eligible:
            return None, None
        dt, value = eligible[-1]
        if (target.date() - dt.date()).days > 7:
            return None, None
        return dt.date().isoformat(), value

    date30, price30 = point_before(30)
    date90, price90 = point_before(90)

    def return_pct(old: float | None) -> float | None:
        if old is None or old <= 0:
            return None
        return (current / old - 1.0) * 100.0

    return {
        "asOf": latest_dt.date().isoformat(),
        "current": current,
        "date30": date30,
        "price30": price30,
        "return30": return_pct(price30),
        "date90": date90,
        "price90": price90,
        "return90": return_pct(price90),
        "source": "Yahoo Finance chart adjusted close",
    }


def history_point(snapshot: dict, period: str) -> dict | None:
    row = (snapshot.get("periods") or {}).get(period) or {}
    earnings = row.get("earnings") or {}
    revenue = row.get("revenue") or {}
    eps = earnings.get("avg")
    sales = revenue.get("avg")
    if eps is None and sales is None:
        return None
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "eps": eps,
        "revenue": sales,
        "epsAnalysts": earnings.get("analysts"),
        "revenueAnalysts": revenue.get("analysts"),
    }


def prune(rows: list[dict]) -> list[dict]:
    rows = [x for x in rows if isinstance(x, dict) and x.get("date")]
    rows.sort(key=lambda x: x["date"])
    return rows[-MAX_HISTORY_DAYS:]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    old_history = load_json(OUT_HISTORY)
    history = old_history.get("history") or {}
    quotes: dict[str, dict] = {}
    errors: dict[str, str] = {}
    price_errors: dict[str, str] = {}

    symbols = selected_symbols()
    for index, symbol in enumerate(symbols, start=1):
        try:
            row = fetch_live_consensus(symbol)
            try:
                row["priceTrend"] = fetch_price_trend(symbol)
            except Exception as price_exc:
                price_errors[symbol] = str(price_exc)
                print(f"[{index}/{len(symbols)}] {symbol} PRICE ERROR {price_exc}")
            quotes[symbol] = row
            for period in ("0y", "+1y"):
                point = history_point(row, period)
                if not point:
                    continue
                sym_hist = history.setdefault(symbol, {})
                rows = list(sym_hist.get(period) or [])
                if rows and rows[-1].get("date") == point["date"]:
                    rows[-1] = point
                else:
                    rows.append(point)
                sym_hist[period] = prune(rows)
            print(f"[{index}/{len(symbols)}] {symbol} OK")
        except Exception as exc:
            errors[symbol] = str(exc)
            print(f"[{index}/{len(symbols)}] {symbol} ERROR {exc}")
        time.sleep(0.08)

    generated = datetime.now(timezone.utc).isoformat()
    cache_payload = {
        "generatedAt": generated,
        "count": len(quotes),
        "errors": errors,
        "priceErrors": price_errors,
        "source": "Yahoo Finance earningsTrend + adjusted price chart",
        "quotes": quotes,
    }
    history_payload = {
        "generatedAt": generated,
        "retentionDays": MAX_HISTORY_DAYS,
        "history": history,
    }
    OUT_CACHE.write_text(json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUT_HISTORY.write_text(json.dumps(history_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    price_ready = sum(1 for row in quotes.values() if (row.get("priceTrend") or {}).get("return30") is not None)
    print(f"wrote {len(quotes)}/{len(symbols)} consensus snapshots; errors={len(errors)} price_ready={price_ready} price_errors={len(price_errors)}")

    for symbol in ("AAPL", "NVDA", "005930.KS", "000660.KS"):
        if symbol not in quotes:
            raise SystemExit(f"required consensus missing: {symbol}: {errors.get(symbol)}")


if __name__ == "__main__":
    main()
