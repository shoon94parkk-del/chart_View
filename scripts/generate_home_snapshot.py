"""Generate a persistent home-market snapshot outside the web process.

GitHub Actions runs this periodically so the web app can serve the latest
successful snapshot even when Render has been asleep since the last visit.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "home_snapshot.json"
TICKERS = ["005930.KS", "000660.KS", "NVDA", "AAPL", "MSFT", "META", "TSLA", "GOOGL"]
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch(ticker: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    response = requests.get(url, params={"range": "5d", "interval": "1d", "includePrePost": "false"}, headers=HEADERS, timeout=15)
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no result for {ticker}")
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    previous = meta.get("previousClose") or meta.get("chartPreviousClose")
    if price is None and previous is None:
        raise RuntimeError(f"Yahoo returned no price for {ticker}")
    if price is None:
        price = previous
    change = ((float(price) - float(previous)) / float(previous) * 100) if previous else None
    market_time = meta.get("regularMarketTime")
    as_of = datetime.fromtimestamp(int(market_time), timezone.utc).isoformat() if market_time else None
    return {"ticker": ticker, "name": meta.get("shortName") or meta.get("longName") or ticker,
            "price": round(float(price), 4), "change": round(change, 4) if change is not None else None,
            "marketCap": meta.get("regularMarketVolume") or 0, "asOf": as_of, "stale": False}


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
    payload = {"generatedAt": datetime.now(timezone.utc).isoformat(), "source": "github-actions-yahoo-chart",
               "heatmap": {"results": rows}, "errors": errors}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote home snapshot: {len(rows)}/{len(TICKERS)} quotes")


if __name__ == "__main__":
    main()
