"""Fast market-data helpers used by the Render web app.

Design goals:
- price/chart: Yahoo v8 chart endpoint (no crumb required)
- valuation: Yahoo fundamentals-timeseries (no crumb) as the reliable base
- forward estimates/dividend/detail: quoteSummary with a cookie+crumb session when available
- no paid API key required
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}

_names_lock = threading.Lock()
_names: dict[str, str] | None = None
_cache_lock = threading.Lock()
_compare_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_valuation_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_auth_lock = threading.Lock()
_auth_state: dict[str, Any] = {"cookies": None, "crumb": None, "timestamp": 0.0}


def _local_names() -> dict[str, str]:
    global _names
    if _names is not None:
        return _names
    with _names_lock:
        if _names is not None:
            return _names
        result: dict[str, str] = {}
        try:
            path = os.path.join(os.path.dirname(__file__), "static", "data", "screener.json")
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            for row in payload.get("stocks", []):
                symbol = str(row.get("symbol") or "").upper()
                name = str(row.get("name") or "").strip()
                if symbol and name:
                    result[symbol] = name
        except Exception as exc:
            print(f"[MarketData] local name cache unavailable: {exc}")
        _names = result
        return result


def _raw(value: Any) -> Any:
    if isinstance(value, dict) and "raw" in value:
        return value.get("raw")
    return value


def _positive(value: Any) -> float | None:
    try:
        n = float(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _http_json(url: str, params: dict[str, Any] | None = None, timeout: float = 9.0) -> dict[str, Any]:
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _chart_result(symbol: str, *, period: str = "5d", interval: str = "1d", start: str | None = None, end: str | None = None, events: str | None = None) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params: dict[str, Any] = {"interval": interval, "includePrePost": "false"}
    if start and end:
        # Yahoo period2 is exclusive, so include the user's end date by adding one day.
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        params.update({"period1": int(start_dt.timestamp()), "period2": int(end_dt.timestamp())})
    else:
        params["range"] = period
    if events:
        params["events"] = events
    data = _http_json(url, params=params)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError(f"Yahoo chart returned no result for {symbol}")
    return result


def fetch_compare_stock(symbol: str, period: str = "1mo", start: str | None = None, end: str | None = None) -> dict[str, Any] | None:
    symbol = symbol.strip().upper()
    if not symbol:
        return None

    interval_map = {
        "1d": "5m", "5d": "15m", "1mo": "1h",
        "3mo": "1d", "6mo": "1d", "1y": "1d", "max": "1d",
    }
    interval = "1d" if start and end else interval_map.get(period, "1d")
    key = f"{symbol}|{period}|{start or ''}|{end or ''}|{interval}"
    now = time.time()
    with _cache_lock:
        cached = _compare_cache.get(key)
        if cached and now - cached[0] < 60:
            return cached[1]

    try:
        result = _chart_result(symbol, period=period, interval=interval, start=start, end=end)
        meta = result.get("meta", {})
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        points = [(int(ts), float(close)) for ts, close in zip(timestamps, closes) if close is not None and float(close) > 0]
        if not points:
            value = None
        else:
            first = points[0][1]
            line_data = [{"time": ts, "value": round((close - first) / first * 100, 2)} for ts, close in points]
            last_close = points[-1][1]
            price = _positive(meta.get("regularMarketPrice")) or last_close
            name = _local_names().get(symbol) or meta.get("shortName") or meta.get("longName") or symbol
            value = {
                "ticker": symbol,
                "name": name,
                "price": round(float(price), 2),
                "return": round((last_close - first) / first * 100, 2),
                "data": line_data,
                "currency": meta.get("currency"),
                "source": "Yahoo Chart",
            }
    except Exception as exc:
        print(f"[MarketData] chart failed {symbol}: {exc}")
        value = None

    with _cache_lock:
        _compare_cache[key] = (now, value)
    return value


def _ensure_yahoo_auth(force: bool = False) -> tuple[dict[str, str], str] | None:
    now = time.time()
    with _auth_lock:
        if not force and _auth_state.get("crumb") and now - float(_auth_state.get("timestamp") or 0) < 1800:
            return dict(_auth_state["cookies"]), str(_auth_state["crumb"])
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            # fc.yahoo.com commonly answers 404 while still setting the A3 cookie.
            session.get("https://fc.yahoo.com", timeout=6, allow_redirects=True)
            crumb_res = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=6)
            crumb_res.raise_for_status()
            crumb = crumb_res.text.strip()
            if not crumb or "<" in crumb:
                raise ValueError("invalid crumb response")
            cookies = requests.utils.dict_from_cookiejar(session.cookies)
            if not cookies:
                raise ValueError("Yahoo cookie not issued")
            _auth_state.update({"cookies": cookies, "crumb": crumb, "timestamp": now})
            return dict(cookies), crumb
        except Exception as exc:
            print(f"[MarketData] Yahoo detail auth unavailable: {exc}")
            _auth_state.update({"cookies": None, "crumb": None, "timestamp": now})
            return None


def _quote_summary(symbol: str) -> dict[str, Any] | None:
    auth = _ensure_yahoo_auth()
    if not auth:
        return None
    cookies, crumb = auth
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
    params = {
        "modules": "price,summaryDetail,defaultKeyStatistics,financialData,assetProfile",
        "crumb": crumb,
    }
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, headers=HEADERS, cookies=cookies, timeout=8)
            if r.status_code in (401, 403) and attempt == 0:
                auth = _ensure_yahoo_auth(force=True)
                if not auth:
                    return None
                cookies, crumb = auth
                params["crumb"] = crumb
                continue
            r.raise_for_status()
            return (r.json().get("quoteSummary", {}).get("result") or [None])[0]
        except Exception as exc:
            if attempt:
                print(f"[MarketData] quoteSummary fallback skipped for {symbol}: {exc}")
    return None


FUND_TYPES = [
    "trailingMarketCap", "trailingPeRatio", "trailingPsRatio",
    "trailingBasicEPS", "trailingDilutedEPS", "trailingTotalRevenue",
    "trailingEBITDA", "trailingNetIncome", "trailingOperatingIncome",
    "quarterlyStockholdersEquity", "quarterlyOrdinarySharesNumber", "quarterlyNetDebt",
    "annualStockholdersEquity", "annualOrdinarySharesNumber", "annualNetDebt",
]


def _fundamentals(symbol: str) -> dict[str, float]:
    url = f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
    params = {
        "symbol": symbol,
        "type": ",".join(FUND_TYPES),
        "period1": 0,
        "period2": int(time.time()),
    }
    data = _http_json(url, params=params)
    out: dict[str, float] = {}
    for item in data.get("timeseries", {}).get("result", []):
        typelist = item.get("meta", {}).get("type") or []
        if not typelist:
            continue
        typ = typelist[0]
        values = item.get(typ) or []
        if not values:
            continue
        raw = (values[-1].get("reportedValue") or {}).get("raw")
        n = _number(raw)
        if n is not None:
            out[typ] = n
    return out


def _naver_valuation(symbol: str) -> dict[str, Any]:
    if not (symbol.endswith(".KS") or symbol.endswith(".KQ")):
        return {}
    try:
        from bs4 import BeautifulSoup
        code = symbol.split(".")[0]
        r = requests.get(
            "https://finance.naver.com/item/main.naver",
            params={"code": code},
            headers={"User-Agent": UA},
            timeout=5,
        )
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        out: dict[str, Any] = {}
        name = soup.select_one("div.wrap_company h2 a")
        if name:
            out["name"] = name.get_text(strip=True)
        for selector, key in (("#_per", "trailingPE"), ("#_pbr", "pbr"), ("#_dvr", "dividendYield")):
            tag = soup.select_one(selector)
            if not tag:
                continue
            text = tag.get_text(strip=True).replace(",", "").replace("%", "")
            try:
                out[key] = float(text)
            except (TypeError, ValueError):
                pass
        return out
    except Exception:
        return {}


def fetch_valuation_snapshot(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    now = time.time()
    with _cache_lock:
        cached = _valuation_cache.get(symbol)
        if cached and now - cached[0] < 300:
            return cached[1]

    chart_meta: dict[str, Any] = {}
    last_close: float | None = None
    try:
        chart = _chart_result(symbol, period="5d", interval="1d")
        chart_meta = chart.get("meta", {})
        closes = ((chart.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
        good = [float(v) for v in closes if v is not None and float(v) > 0]
        last_close = good[-1] if good else None
    except Exception as exc:
        print(f"[MarketData] valuation chart failed {symbol}: {exc}")

    try:
        fund = _fundamentals(symbol)
    except Exception as exc:
        print(f"[MarketData] fundamentals failed {symbol}: {exc}")
        fund = {}

    detail = _quote_summary(symbol) or {}
    summary = detail.get("summaryDetail") or {}
    stats = detail.get("defaultKeyStatistics") or {}
    financial = detail.get("financialData") or {}
    price_block = detail.get("price") or {}
    profile = detail.get("assetProfile") or {}

    price = (
        _positive(_raw(price_block.get("regularMarketPrice")))
        or _positive(chart_meta.get("regularMarketPrice"))
        or last_close
        or 0.0
    )
    market_cap = _positive(_raw(summary.get("marketCap"))) or _positive(_raw(price_block.get("marketCap"))) or _positive(fund.get("trailingMarketCap"))
    trailing_pe = _positive(_raw(summary.get("trailingPE"))) or _positive(fund.get("trailingPeRatio"))
    forward_pe = _positive(_raw(summary.get("forwardPE"))) or _positive(_raw(stats.get("forwardPE")))
    trailing_eps = _number(_raw(stats.get("trailingEps"))) or _number(fund.get("trailingDilutedEPS")) or _number(fund.get("trailingBasicEPS"))
    forward_eps = _number(_raw(stats.get("forwardEps")))
    psr = _positive(_raw(summary.get("priceToSalesTrailing12Months"))) or _positive(fund.get("trailingPsRatio"))

    equity = _positive(fund.get("quarterlyStockholdersEquity")) or _positive(fund.get("annualStockholdersEquity"))
    shares = _positive(fund.get("quarterlyOrdinarySharesNumber")) or _positive(fund.get("annualOrdinarySharesNumber"))
    book_value = _number(_raw(stats.get("bookValue")))
    if book_value is None and equity and shares:
        book_value = equity / shares
    pbr = _positive(_raw(stats.get("priceToBook")))
    if pbr is None and price and book_value and book_value > 0:
        pbr = price / book_value

    ebitda = _positive(_raw(financial.get("ebitda"))) or _positive(fund.get("trailingEBITDA"))
    enterprise_value = _positive(_raw(stats.get("enterpriseValue")))
    net_debt = _number(fund.get("quarterlyNetDebt"))
    if net_debt is None:
        net_debt = _number(fund.get("annualNetDebt"))
    if enterprise_value is None and market_cap and net_debt is not None:
        enterprise_value = market_cap + net_debt
    ev_ebitda = enterprise_value / ebitda if enterprise_value and ebitda else None

    dividend_yield = _number(_raw(summary.get("dividendYield")))
    # Yahoo quoteSummary returns dividendYield as a fraction; UI expects percentage units.
    if dividend_yield is not None:
        dividend_yield *= 100

    roe = _number(_raw(financial.get("returnOnEquity")))
    if roe is not None:
        roe *= 100
    elif equity:
        net_income = _number(fund.get("trailingNetIncome"))
        if net_income is not None:
            roe = net_income / equity * 100

    operating_margin = _number(_raw(financial.get("operatingMargins")))
    if operating_margin is not None:
        operating_margin *= 100
    else:
        revenue = _positive(fund.get("trailingTotalRevenue"))
        operating_income = _number(fund.get("trailingOperatingIncome"))
        if revenue and operating_income is not None:
            operating_margin = operating_income / revenue * 100

    name = (
        _local_names().get(symbol)
        or price_block.get("shortName")
        or price_block.get("longName")
        or chart_meta.get("shortName")
        or chart_meta.get("longName")
        or symbol
    )

    # Last fallback for Korean ratios when Yahoo has a sparse record.
    naver = _naver_valuation(symbol) if (trailing_pe is None or pbr is None or dividend_yield is None) else {}
    trailing_pe = trailing_pe or _positive(naver.get("trailingPE"))
    pbr = pbr or _positive(naver.get("pbr"))
    if dividend_yield is None:
        dividend_yield = _number(naver.get("dividendYield"))
    if naver.get("name") and name == symbol:
        name = naver["name"]

    data = {
        "ticker": symbol,
        "name": name,
        "price": round(price, 2) if price else None,
        "currency": price_block.get("currency") or chart_meta.get("currency") or ("KRW" if symbol.endswith((".KS", ".KQ")) else None),
        "marketCap": round(market_cap, 2) if market_cap else None,
        "sector": profile.get("sector") or "",
        "trailingPE": round(trailing_pe, 2) if trailing_pe is not None else None,
        "forwardPE": round(forward_pe, 2) if forward_pe is not None else None,
        "trailingEPS": round(trailing_eps, 2) if trailing_eps is not None else None,
        "forwardEPS": round(forward_eps, 2) if forward_eps is not None else None,
        "pbr": round(pbr, 2) if pbr is not None else None,
        "bookValue": round(book_value, 2) if book_value is not None else None,
        "psr": round(psr, 2) if psr is not None else None,
        "evEbitda": round(ev_ebitda, 2) if ev_ebitda is not None else None,
        "dividendYield": round(dividend_yield, 2) if dividend_yield is not None else None,
        "roe": round(roe, 2) if roe is not None else None,
        "operatingMargin": round(operating_margin, 2) if operating_margin is not None else None,
        "dataSource": "Yahoo Chart + Fundamentals" + (" + QuoteSummary" if detail else "") + (" + Naver" if naver else ""),
    }
    with _cache_lock:
        _valuation_cache[symbol] = (now, data)
    return data
