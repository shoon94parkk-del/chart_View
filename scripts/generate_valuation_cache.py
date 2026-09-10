"""Build a small daily Yahoo quote cache outside Render.

Render's shared free IP can be rate-limited by Yahoo's crumb endpoint. GitHub Actions
can fetch one authenticated multi-symbol quote once a day; the web service then
uses this tiny JSON for forward PE and dividend/detail fields without waiting.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "valuation_cache.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def collect_symbols() -> list[str]:
    symbols: set[str] = {"AAPL", "NVDA"}
    for path in [ROOT / "templates" / "index.html", ROOT / "main.py"]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        symbols.update(re.findall(r"addGlobalTicker\(['\"]([^'\"]+)", text))
        symbols.update(re.findall(r'["\']symbol["\']\s*:\s*["\']([^"\']+)', text))
    # Avoid accidental indexes/garbage; keep normal Yahoo-style symbols only.
    return sorted(s.upper() for s in symbols if re.fullmatch(r"[A-Za-z0-9.^=-]+", s))


def main() -> None:
    symbols = collect_symbols()
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
    session.get("https://fc.yahoo.com", timeout=10, allow_redirects=True)
    crumb_res = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
    crumb_res.raise_for_status()
    crumb = crumb_res.text.strip()
    if not crumb or "<" in crumb:
        raise RuntimeError("Yahoo crumb was invalid")

    rows: dict[str, dict] = {}
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i+50]
        r = session.get(
            "https://query1.finance.yahoo.com/v7/finance/quote",
            params={"symbols": ",".join(chunk), "crumb": crumb},
            timeout=20,
        )
        r.raise_for_status()
        for q in r.json().get("quoteResponse", {}).get("result", []):
            symbol = str(q.get("symbol") or "").upper()
            if not symbol:
                continue
            rows[symbol] = {
                "shortName": q.get("shortName") or q.get("longName") or symbol,
                "currency": q.get("currency"),
                "regularMarketPrice": q.get("regularMarketPrice"),
                "marketCap": q.get("marketCap"),
                "trailingPE": q.get("trailingPE"),
                "forwardPE": q.get("forwardPE"),
                "priceToBook": q.get("priceToBook"),
                "bookValue": q.get("bookValue"),
                "epsTrailingTwelveMonths": q.get("epsTrailingTwelveMonths"),
                "epsForward": q.get("epsForward"),
                "dividendYield": q.get("dividendYield"),
                "averageAnalystRating": q.get("averageAnalystRating"),
            }
        time.sleep(0.15)

    if len(rows) < 10:
        raise RuntimeError(f"Yahoo cache returned too few symbols: {len(rows)}")
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "quotes": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(rows)} quote snapshots -> {OUT}")


if __name__ == "__main__":
    main()
