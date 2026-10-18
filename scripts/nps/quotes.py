#!/usr/bin/env python3
"""Fetch bounded Yahoo daily prices and revalue a frozen 13F share basket.

Python standard library only. Historical Yahoo `close` is split-adjusted, not
dividend-adjusted. `adjclose` additionally reflects cash distributions. Retained
raw responses and SEC report reconciliation make those conventions reviewable.
"""

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
BENCHMARKS = ["VTI", "ACWI", "VXUS", "ITOT"]
ACTION_REVIEWS = {}
DEADLINE = float("inf")


def utcnow():
    return dt.datetime.now(UTC).isoformat()


def symbol_for(ticker):
    # US share-class notation differs between 13f.info and Yahoo.
    return str(ticker).strip().upper().replace(".", "-")


def finite_positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def chart_url(symbol, report_date, valuation_date):
    start = dt.datetime.combine(dt.date.fromisoformat(report_date) - dt.timedelta(days=5), dt.time(), UTC)
    # period2 is exclusive, hence midnight after the final requested session.
    stop = dt.datetime.combine(dt.date.fromisoformat(valuation_date) + dt.timedelta(days=1), dt.time(), UTC)
    params = urllib.parse.urlencode({"period1": int(start.timestamp()), "period2": int(stop.timestamp()),
        "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?{params}"


def read_chart(symbol, dates, cache_dir, refresh=False):
    url = chart_url(symbol, dates[0], dates[-1])
    path = cache_dir / f"{symbol}.json"
    payload = None
    if path.exists() and not refresh:
        try:
            cached = json.loads(path.read_text())
            result = cached.get("chart", {}).get("result")
            if result and result[0].get("timestamp"):
                timestamps = result[0]["timestamp"]
                cache_timezone = ZoneInfo(result[0].get("meta", {}).get("exchangeTimezoneName", "America/New_York"))
                first = dt.datetime.fromtimestamp(min(timestamps), cache_timezone).date().isoformat()
                last = dt.datetime.fromtimestamp(max(timestamps), cache_timezone).date().isoformat()
                if first <= dates[0] and last >= dates[-1]:
                    payload = cached
        except (ValueError, TypeError, KeyError):
            pass
    if payload is None:
        last_error = None
        for attempt in range(2):
            if time.monotonic() >= DEADLINE:
                raise TimeoutError("Collection deadline reached")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (historical portfolio research)"})
                with urllib.request.urlopen(request, timeout=max(0.1, min(12, DEADLINE-time.monotonic()))) as response:
                    raw = response.read()
                payload = json.loads(raw)
                if payload.get("chart", {}).get("error"):
                    raise ValueError(str(payload["chart"]["error"]))
                path.write_bytes(raw)
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as error:
                last_error = str(error)
                if attempt < 1:
                    time.sleep(0.5 * (attempt + 1))
        if payload is None:
            raise ValueError(last_error)
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    timezone = ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    timestamps = result.get("timestamp", [])
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    adjusted = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    points = {}
    for index, timestamp in enumerate(timestamps):
        date = dt.datetime.fromtimestamp(timestamp, timezone).date().isoformat()
        if date > dates[-1]:
            continue  # Never read a later observation into this valuation.
        points[date] = {"date": date, "timestamp": timestamp,
            "close": closes[index] if index < len(closes) else None,
            "adjustedClose": adjusted[index] if index < len(adjusted) else None}
    prices = {key: points.get(date) for key, date in zip(["report", "baseline", "current"], dates)}
    events = {"splits": [], "dividends": []}
    for kind in events:
        for event in result.get("events", {}).get(kind, {}).values():
            date = dt.datetime.fromtimestamp(event["date"], timezone).date().isoformat()
            if dates[0] < date <= dates[-1]:
                events[kind].append({**event, "date": date, "timestamp": event["date"]})
        events[kind].sort(key=lambda event: event["date"])
    flags = []
    if meta.get("currency") != "USD":
        flags.append("non_usd_quote")
    if meta.get("instrumentType") not in ("EQUITY", "ETF", "MUTUALFUND"):
        flags.append("unsupported_instrument_type")
    for key, price in prices.items():
        if not price:
            flags.append(f"missing_exact_{key}_date")
        elif not all(finite_positive(price[field]) for field in ("close", "adjustedClose")):
            flags.append(f"invalid_{key}_price")
    good_prices = not any(flag.startswith(("missing_", "invalid_")) for flag in flags)
    output = {"symbol": symbol, "name": meta.get("longName", meta.get("shortName")),
        "currency": meta.get("currency"), "exchange": meta.get("fullExchangeName"),
        "instrumentType": meta.get("instrumentType"), "prices": prices, "events": events,
        "valid": not flags, "flags": flags, "sourceUrl": url,
        "retrievedAt": dt.datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "points": points, "rawSha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if good_prices:
        output["priceReturn"] = prices["current"]["close"] / prices["baseline"]["close"] - 1
        output["totalReturn"] = prices["current"]["adjustedClose"] / prices["baseline"]["adjustedClose"] - 1
        output["reportToBaselinePriceReturn"] = prices["baseline"]["close"] / prices["report"]["close"] - 1
        output["reportToBaselineTotalReturn"] = prices["baseline"]["adjustedClose"] / prices["report"]["adjustedClose"] - 1
    return output


def split_factor(events, after, through):
    factor = 1.0
    for event in events:
        if after < event["date"] <= through:
            factor *= float(event["numerator"]) / float(event["denominator"])
    return factor


def price_holding(holding, chart, dates, tolerance):
    ticker = str(holding.get("ticker") or holding.get("symbol") or "")
    output = {**holding, "ticker": ticker, "reportValueUSD": float(holding.get("valueUsd", holding.get("reportValueUSD", holding.get("value", 0)))),
        "shares": float(holding.get("shares", 0))}
    action_review = ACTION_REVIEWS.get(symbol_for(ticker))
    if action_review and (not action_review.get("eventDate") or dates[0] < action_review["eventDate"] <= dates[2]):
        output["corporateActionReview"] = action_review
    if str(holding.get("class", "")).strip().upper().startswith(("W EXP", "WARRANT", "WT ")):
        output.update({"valid": False, "flags": ["warrant_not_revalued_as_equity"], "error": "Warrant requires its own security history; ordinary equity prices are not substituted."})
        return output
    if not chart or "error" in chart:
        output.update({"valid": False, "flags": ["price_fetch_failed"], "error": (chart or {}).get("error", "No mapped ticker")})
        return output
    output.update(chart)
    output["flags"] = list(chart["flags"])
    if action_review and dates[0] < action_review["eventDate"] <= dates[2]:
        output["corporateActionReview"] = action_review
        if action_review["decision"] == "exclude":
            output["flags"].append("complex_corporate_action_unmodeled")
            output["valid"] = False
            return output
    for event in chart["events"]["splits"]:
        factor = float(event["numerator"]) / float(event["denominator"])
        ordinary_split = math.isclose(factor, round(factor)) or math.isclose(1 / factor, round(1 / factor))
        verified_stock_dividend = action_review and action_review["decision"] == "allow_stock_dividend" and event["date"] == action_review["eventDate"] and math.isclose(factor, action_review["verifiedFactor"])
        if not ordinary_split and not verified_stock_dividend:
            output["flags"].append("unverified_nonstandard_corporate_action")
            output["valid"] = False
            return output
    if holding.get("putCall"):
        output["flags"].append("option_not_revalued_as_equity")
    if holding.get("shareType", "SH") != "SH":
        output["flags"].append("non_share_security")
    if not finite_positive(output["shares"]) or not finite_positive(output["reportValueUSD"]):
        output["flags"].append("invalid_report_value_or_shares")
    if not chart["valid"] or "invalid_report_value_or_shares" in output["flags"]:
        output["valid"] = False
        return output
    after_report = split_factor(chart["events"]["splits"], dates[0], dates[2])
    after_baseline = split_factor(chart["events"]["splits"], dates[1], dates[2])
    output["splitFactorAfterReport"] = after_report
    output["splitFactorAfterBaseline"] = after_baseline
    # Yahoo historical closes are on the last-session split basis. All quantities
    # used with these closes must be on that same basis, including the July mark.
    current_basis_shares = output["shares"] * after_report
    output["sharesOnCurrentBasis"] = current_basis_shares
    output["actualSharesAtBaseline"] = output["shares"] * after_report / after_baseline
    calculated = current_basis_shares * output["prices"]["report"]["close"]
    relative_error = calculated / output["reportValueUSD"] - 1
    output["reportPriceCheck"] = {"impliedClose": output["reportValueUSD"] / current_basis_shares,
        "calculatedValueUSD": calculated, "relativeError": relative_error}
    if abs(relative_error) > tolerance:
        output["flags"].append("report_price_mismatch")
    output["baselineMarketValueUSD"] = current_basis_shares * output["prices"]["baseline"]["close"]
    output["currentMarketValueUSD"] = current_basis_shares * output["prices"]["current"]["close"]
    output["currentTotalReturnValueUSD"] = output["baselineMarketValueUSD"] * (1 + output["totalReturn"])
    output["valid"] = not output["flags"]
    return output

