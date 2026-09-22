"""Generate a persistent Home market snapshot outside the web process.

The snapshot is a cold-start/fallback asset. Its change field MUST mean
one trading-session percent change, never the selected chart-range return.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "home_snapshot.json"
TICKERS = [
    "005930.KS", "000660.KS", "207940.KS", "005380.KS",
    "000270.KS", "373220.KS", "035420.KS", "068270.KS",
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN",
    "TSM", "META", "AVGO", "TSLA", "AMD",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://m.stock.naver.com/",
}
VALUATION_CACHE = ROOT / "static" / "data" / "valuation_cache.json"


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _is_korean(ticker: str) -> bool:
    return ticker.endswith((".KS", ".KQ")) and ticker.split(".", 1)[0].isdigit()


def load_market_caps() -> dict[str, float]:
    """Use the daily valuation cache for actual market cap."""
    try:
        payload = json.loads(VALUATION_CACHE.read_text(encoding="utf-8"))
        quotes = payload.get("quotes") or {}
        return {
            ticker: float((quotes.get(ticker) or {}).get("marketCap") or 0)
            for ticker in TICKERS
        }
    except Exception as exc:
        print(f"valuation market-cap cache unavailable: {exc}")
        return {ticker: 0.0 for ticker in TICKERS}


MARKET_CAPS = load_market_caps()


def _fetch_naver(ticker: str) -> dict:
    code = ticker.split(".", 1)[0]
    response = requests.get(
        f"https://m.stock.naver.com/api/stock/{code}/basic",
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    price = _number(data.get("closePrice"))
    change = _number(data.get("fluctuationsRatio"))
    if price is None:
        raise RuntimeError(f"Naver returned no price for {ticker}")
    return {
        "ticker": ticker,
        "name": str(data.get("stockName") or data.get("itemName") or ticker).strip(),
        "price": round(price, 4),
        "change": round(change, 4) if change is not None else None,
        "marketCap": MARKET_CAPS.get(ticker, 0),
        "asOf": str(data.get("localTradedAt") or "").strip() or datetime.now(timezone.utc).isoformat(),
        "source": "Naver Finance KRX/Koscom",
        "stale": False,
    }


def _fetch_yahoo_daily(ticker: str) -> dict:
    """Compute ONE-session change from the last two daily closes.

    Do not use meta.previousClose/chartPreviousClose for a 5d request: those
    fields can represent the chart-range baseline and produced 5-day returns
    in a UI labeled "today".
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    response = requests.get(
        url,
        params={"range": "5d", "interval": "1d", "includePrePost": "false"},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no result for {ticker}")

    meta = result.get("meta") or {}
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    good = [float(value) for value in closes if _number(value) is not None and float(value) > 0]
    if len(good) < 2:
        raise RuntimeError(f"Yahoo returned fewer than two daily closes for {ticker}")

    current = _number(meta.get("regularMarketPrice"))
    if current is None:
        current = good[-1]
    previous = good[-2]
    change = (current - previous) / previous * 100

    market_time = meta.get("regularMarketTime")
    as_of = datetime.fromtimestamp(int(market_time), timezone.utc).isoformat() if market_time else None
    return {
        "ticker": ticker,
        "name": meta.get("shortName") or meta.get("longName") or ticker,
        "price": round(float(current), 4),
        "change": round(float(change), 4),
        "marketCap": MARKET_CAPS.get(ticker, 0),
        "asOf": as_of,
        "source": "Yahoo daily close",
        "stale": False,
    }


def fetch(ticker: str) -> dict:
    if _is_korean(ticker):
        try:
            return _fetch_naver(ticker)
        except Exception as exc:
            print(f"Naver snapshot fallback to Yahoo for {ticker}: {exc}")
    return _fetch_yahoo_daily(ticker)


def main() -> None:
    rows = []
    errors = []
    for ticker in TICKERS:
        try:
            rows.append(fetch(ticker))
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
        time.sleep(0.2)
    if len(rows) < len(TICKERS) * 0.75:
        raise RuntimeError(f"too few successful quotes: {len(rows)}/{len(TICKERS)}; {errors}")
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "github-actions-daily-change-v67",
        "heatmap": {"results": rows},
        "errors": errors,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote home snapshot: {len(rows)}/{len(TICKERS)} quotes")


if __name__ == "__main__":
    main()
