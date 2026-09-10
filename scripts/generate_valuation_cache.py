"""Build a small daily Yahoo valuation cache outside Render.

Render free/shared IPs can be rate-limited by Yahoo detail endpoints. GitHub Actions
fetches the authenticated data once a day and stores a small JSON cache. The fast
multi-symbol quote endpoint is used first; missing forward estimates (common for
.KS/.KQ symbols) are backfilled from Yahoo quoteSummary.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "data" / "valuation_cache.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}


def collect_symbols() -> list[str]:
    symbols: set[str] = {"AAPL", "NVDA", "005930.KS", "000660.KS"}
    for path in [ROOT / "templates" / "index.html", ROOT / "main.py"]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        symbols.update(re.findall(r"addGlobalTicker\(['\"]([^'\"]+)", text))
        symbols.update(re.findall(r'["\']symbol["\']\s*:\s*["\']([^"\']+)', text))
    return sorted(s.upper() for s in symbols if re.fullmatch(r"[A-Za-z0-9.^=-]+", s))


def raw(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("raw")
    return value


def first(*values: Any) -> Any:
    for value in values:
        value = raw(value)
        if value is not None:
            return value
    return None


def yahoo_session() -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update(HEADERS)
    # fc.yahoo.com may return 404 but still sets the cookie needed by getcrumb.
    session.get("https://fc.yahoo.com", timeout=10, allow_redirects=True)
    crumb_res = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
    crumb_res.raise_for_status()
    crumb = crumb_res.text.strip()
    if not crumb or "<" in crumb:
        raise RuntimeError("Yahoo crumb was invalid")
    return session, crumb


def quote_row(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "shortName": q.get("shortName") or q.get("longName") or q.get("symbol"),
        "currency": q.get("currency"),
        "regularMarketPrice": q.get("regularMarketPrice"),
        "marketCap": q.get("marketCap"),
        "trailingPE": q.get("trailingPE"),
        "forwardPE": q.get("forwardPE"),
        "priceToBook": q.get("priceToBook"),
        "bookValue": q.get("bookValue"),
        "epsTrailingTwelveMonths": q.get("epsTrailingTwelveMonths"),
        "epsForward": q.get("epsForward"),
        # v7/quote exposes dividendYield in percentage units (0.56 == 0.56%).
        "dividendYield": q.get("dividendYield"),
        "averageAnalystRating": q.get("averageAnalystRating"),
        "forwardPESource": "Yahoo quote" if q.get("forwardPE") is not None else None,
    }


def fetch_quote_summary(session: requests.Session, crumb: str, symbol: str) -> dict[str, Any] | None:
    params = {
        "modules": "price,summaryDetail,defaultKeyStatistics,financialData",
        "crumb": crumb,
    }
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            r = session.get(
                f"https://{host}/v10/finance/quoteSummary/{symbol}",
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            result = (r.json().get("quoteSummary", {}).get("result") or [None])[0]
            if result:
                return result
        except Exception as exc:
            print(f"quoteSummary {host} failed for {symbol}: {exc}")
    return None


def backfill_detail(row: dict[str, Any], detail: dict[str, Any]) -> None:
    summary = detail.get("summaryDetail") or {}
    stats = detail.get("defaultKeyStatistics") or {}
    price = detail.get("price") or {}

    mapping = {
        "shortName": first(price.get("shortName"), price.get("longName")),
        "currency": first(price.get("currency")),
        "regularMarketPrice": first(price.get("regularMarketPrice")),
        "marketCap": first(summary.get("marketCap"), price.get("marketCap")),
        "trailingPE": first(summary.get("trailingPE")),
        "forwardPE": first(summary.get("forwardPE"), stats.get("forwardPE")),
        "priceToBook": first(stats.get("priceToBook")),
        "bookValue": first(stats.get("bookValue")),
        "epsTrailingTwelveMonths": first(stats.get("trailingEps")),
        "epsForward": first(stats.get("forwardEps")),
    }
    for key, value in mapping.items():
        if row.get(key) is None and value is not None:
            row[key] = value

    # quoteSummary uses a fraction for dividendYield; cache uses percentage units.
    if row.get("dividendYield") is None:
        div = first(summary.get("dividendYield"))
        if div is not None:
            row["dividendYield"] = float(div) * 100

    if row.get("forwardPE") is not None:
        row["forwardPESource"] = "Yahoo quoteSummary"
    elif row.get("regularMarketPrice") and row.get("epsForward"):
        try:
            eps = float(row["epsForward"])
            price_value = float(row["regularMarketPrice"])
            if eps > 0 and price_value > 0:
                row["forwardPE"] = price_value / eps
                row["forwardPESource"] = "Yahoo forward EPS (derived)"
        except (TypeError, ValueError, ZeroDivisionError):
            pass


def main() -> None:
    symbols = collect_symbols()
    session, crumb = yahoo_session()

    rows: dict[str, dict[str, Any]] = {}
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i + 50]
        r = session.get(
            "https://query1.finance.yahoo.com/v7/finance/quote",
            params={"symbols": ",".join(chunk), "crumb": crumb},
            timeout=20,
        )
        r.raise_for_status()
        for q in r.json().get("quoteResponse", {}).get("result", []):
            symbol = str(q.get("symbol") or "").upper()
            if symbol:
                rows[symbol] = quote_row(q)
        time.sleep(0.15)

    # Yahoo v7 often omits forwardPE/forwardEPS for Korean equities even when the
    # Yahoo Finance Statistics page has them. Backfill only missing forward data,
    # keeping the normal fast path cheap.
    needs_detail = [
        symbol for symbol, row in rows.items()
        if row.get("forwardPE") is None and (symbol.endswith(".KS") or symbol.endswith(".KQ"))
    ]
    print(f"forward estimate backfill candidates: {len(needs_detail)}")
    for symbol in needs_detail:
        detail = fetch_quote_summary(session, crumb, symbol)
        if detail:
            backfill_detail(rows[symbol], detail)
            print(symbol, "forwardPE=", rows[symbol].get("forwardPE"), "forwardEPS=", rows[symbol].get("epsForward"))
        time.sleep(0.20)

    if len(rows) < 10:
        raise RuntimeError(f"Yahoo cache returned too few symbols: {len(rows)}")

    # These are core regression checks: Yahoo currently publishes forward estimates
    # for Samsung Electronics and SK hynix. Fail the job instead of silently shipping
    # a cache that would show '-' again.
    for core in ("005930.KS", "000660.KS"):
        if core not in rows:
            raise RuntimeError(f"Core Korean symbol missing from Yahoo cache: {core}")
        if rows[core].get("forwardPE") is None:
            print(f"WARNING: Yahoo forward PE still unavailable for {core}; keeping null rather than fabricating a value")

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
