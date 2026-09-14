"""Unified real-time Korean market quotes for Chart View.

All user-visible Korean *current prices* must come from one provider path.
KOSPI/KOSDAQ indices and KRX stocks therefore prefer Naver Finance's
KRX/Koscom-backed endpoints. Yahoo remains a fallback only when Naver is
unavailable. The same short-lived in-process quote is reused by Home,
watchlist/compare and valuation so one symbol cannot show different prices
between screens merely because each screen used a different provider/cache.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
from typing import Any, Callable

import requests

INDEX_MAP = {
    "^KS11": ("KOSPI", "코스피"),
    "^KQ11": ("KOSDAQ", "코스닥"),
}

UA = (
    "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 "
    "Chrome/140.0 Mobile Safari/537.36 ChartView/market-now"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://m.stock.naver.com/",
}

# A single tiny cache is deliberate: every surface sees the same tick while
# avoiding several simultaneous Naver calls when Home/watchlist/detail render.
QUOTE_TTL_SECONDS = 5.0
_quote_lock = threading.Lock()
_quote_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _normalize(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _is_korean_stock(symbol: str) -> bool:
    normalized = _normalize(symbol)
    return normalized.endswith((".KS", ".KQ")) and normalized.split(".", 1)[0].isdigit()


def _cache_get(symbol: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _quote_lock:
        cached = _quote_cache.get(symbol)
        if not cached or now - cached[0] >= QUOTE_TTL_SECONDS:
            return None
        return dict(cached[1])


def _cache_put(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    with _quote_lock:
        _quote_cache[symbol] = (time.monotonic(), dict(row))
        if len(_quote_cache) > 256:
            oldest = min(_quote_cache, key=lambda key: _quote_cache[key][0])
            _quote_cache.pop(oldest, None)
    return dict(row)


def _basic_index_quote(symbol: str) -> dict[str, Any]:
    code, label = INDEX_MAP[symbol]
    response = requests.get(
        f"https://m.stock.naver.com/api/index/{code}/basic",
        headers=HEADERS,
        timeout=(2.5, 4.5),
    )
    response.raise_for_status()
    data = response.json()

    price = _number(data.get("closePrice"))
    change = _number(data.get("fluctuationsRatio"))
    if price is None:
        raise ValueError(f"Naver {code} returned no price")

    traded_at = str(data.get("localTradedAt") or "").strip() or None
    return {
        "ticker": symbol,
        "name": label,
        "price": round(price, 4),
        "change": round(change, 2) if change is not None else None,
        "asOf": traded_at,
        "marketCap": None,
        "currency": "KRW",
        "source": "Naver Finance KRX/Koscom",
        "marketStatus": data.get("marketStatus"),
        "delayTime": data.get("delayTime"),
    }


def _polling_index_quote(symbol: str) -> dict[str, Any]:
    code, label = INDEX_MAP[symbol]
    response = requests.get(
        "https://polling.finance.naver.com/api/realtime",
        params={"query": f"SERVICE_INDEX:{code}"},
        headers=HEADERS,
        timeout=(2.5, 4.5),
    )
    response.raise_for_status()
    payload = response.json()
    areas = (payload.get("result") or {}).get("areas") or []
    rows = (areas[0].get("datas") or []) if areas else []
    row = rows[0] if rows else {}

    raw_price = _number(row.get("nv"))
    change = _number(row.get("cr"))
    if raw_price is None:
        raise ValueError(f"Naver polling {code} returned no price")

    # Index polling values carry two implied decimal places.
    price = raw_price / 100.0
    return {
        "ticker": symbol,
        "name": label,
        "price": round(price, 4),
        "change": round(change, 2) if change is not None else None,
        "asOf": datetime.now(timezone.utc).isoformat(),
        "marketCap": None,
        "currency": "KRW",
        "source": "Naver Finance realtime polling",
        "marketStatus": row.get("ms"),
        "delayTime": 0,
    }


def _basic_stock_quote(symbol: str) -> dict[str, Any]:
    code = symbol.split(".", 1)[0]
    response = requests.get(
        f"https://m.stock.naver.com/api/stock/{code}/basic",
        headers=HEADERS,
        timeout=(2.5, 4.5),
    )
    response.raise_for_status()
    data = response.json()

    price = _number(data.get("closePrice"))
    change = _number(data.get("fluctuationsRatio"))
    if price is None:
        raise ValueError(f"Naver stock {code} returned no price")

    return {
        "ticker": symbol,
        "name": str(data.get("stockName") or data.get("itemName") or symbol).strip(),
        "price": round(price, 4),
        "change": round(change, 2) if change is not None else None,
        "asOf": str(data.get("localTradedAt") or "").strip() or datetime.now(timezone.utc).isoformat(),
        "marketCap": None,
        "currency": "KRW",
        "source": "Naver Finance KRX/Koscom",
        "marketStatus": data.get("marketStatus"),
        "delayTime": data.get("delayTime"),
    }


def _polling_stock_quote(symbol: str) -> dict[str, Any]:
    code = symbol.split(".", 1)[0]
    response = requests.get(
        "https://polling.finance.naver.com/api/realtime",
        params={"query": f"SERVICE_ITEM:{code}"},
        headers=HEADERS,
        timeout=(2.5, 4.5),
    )
    response.raise_for_status()
    payload = response.json()
    areas = (payload.get("result") or {}).get("areas") or []
    rows = (areas[0].get("datas") or []) if areas else []
    row = rows[0] if rows else {}

    price = _number(row.get("nv"))
    change = _number(row.get("cr"))
    if price is None:
        raise ValueError(f"Naver polling stock {code} returned no price")

    return {
        "ticker": symbol,
        "name": str(row.get("nm") or symbol).strip(),
        "price": round(price, 4),
        "change": round(change, 2) if change is not None else None,
        "asOf": datetime.now(timezone.utc).isoformat(),
        "marketCap": None,
        "currency": "KRW",
        "source": "Naver Finance realtime polling",
        "marketStatus": row.get("ms"),
        "delayTime": 0,
    }


def fetch_korean_index_quote(symbol: str) -> dict[str, Any]:
    symbol = _normalize(symbol)
    if symbol not in INDEX_MAP:
        raise ValueError("unsupported Korean index")
    cached = _cache_get(symbol)
    if cached:
        return cached
    try:
        row = _basic_index_quote(symbol)
    except Exception:
        row = _polling_index_quote(symbol)
    return _cache_put(symbol, row)


def fetch_korean_stock_quote(symbol: str) -> dict[str, Any]:
    symbol = _normalize(symbol)
    if not _is_korean_stock(symbol):
        raise ValueError("unsupported Korean stock")
    cached = _cache_get(symbol)
    if cached:
        return cached
    try:
        row = _basic_stock_quote(symbol)
    except Exception:
        row = _polling_stock_quote(symbol)
    return _cache_put(symbol, row)


def _naver_quote(symbol: str) -> dict[str, Any] | None:
    normalized = _normalize(symbol)
    if normalized in INDEX_MAP:
        return fetch_korean_index_quote(normalized)
    if _is_korean_stock(normalized):
        return fetch_korean_stock_quote(normalized)
    return None


def install_patch(market_module: Any) -> None:
    """Use one Naver quote path for every Korean current-price surface."""
    current_quote = getattr(market_module, "fetch_quote_snapshot", None)
    if not callable(current_quote) or getattr(current_quote, "__chartview_korea_realtime__", False):
        return

    original_quote: Callable[..., dict[str, Any] | None] = current_quote
    original_compare: Callable[..., dict[str, Any] | None] | None = getattr(market_module, "fetch_compare_stock", None)
    original_valuation: Callable[..., dict[str, Any]] | None = getattr(market_module, "fetch_valuation_snapshot", None)

    def patched_quote(symbol: str, *args: Any, **kwargs: Any):
        normalized = _normalize(symbol)
        if normalized in INDEX_MAP or _is_korean_stock(normalized):
            try:
                return _naver_quote(normalized)
            except Exception as exc:
                print(f"[KoreaRealtime] Naver quote fallback to Yahoo for {normalized}: {type(exc).__name__}: {exc}")
        return original_quote(symbol, *args, **kwargs)

    patched_quote.__chartview_korea_realtime__ = True  # type: ignore[attr-defined]
    patched_quote.__wrapped__ = original_quote  # type: ignore[attr-defined]
    market_module.fetch_quote_snapshot = patched_quote

    if callable(original_compare):
        def patched_compare(symbol: str, *args: Any, **kwargs: Any):
            normalized = _normalize(symbol)
            value = original_compare(symbol, *args, **kwargs)
            if not _is_korean_stock(normalized):
                return value
            try:
                quote = fetch_korean_stock_quote(normalized)
            except Exception as exc:
                print(f"[KoreaRealtime] compare price fallback to Yahoo for {normalized}: {type(exc).__name__}: {exc}")
                return value

            if value is None:
                return {
                    "ticker": normalized,
                    "name": quote.get("name") or normalized,
                    "price": round(float(quote["price"]), 2),
                    "return": None,
                    "data": [],
                    "currency": "KRW",
                    "source": quote.get("source") or "Naver Finance",
                    "priceBasis": "realtime_quote",
                    "requestedPeriod": kwargs.get("period") or (args[0] if args else "1mo"),
                    "startDate": None,
                    "endDate": None,
                    "observations": 0,
                    "quoteAsOf": quote.get("asOf"),
                    "quoteChange": quote.get("change"),
                }

            merged = dict(value)
            merged["price"] = round(float(quote["price"]), 2)
            merged["currency"] = "KRW"
            merged["quoteSource"] = quote.get("source") or "Naver Finance"
            merged["quoteAsOf"] = quote.get("asOf")
            merged["quoteChange"] = quote.get("change")
            merged["source"] = f"{value.get('source') or 'Yahoo Chart'} + Naver realtime price"
            return merged

        patched_compare.__chartview_korea_realtime__ = True  # type: ignore[attr-defined]
        patched_compare.__wrapped__ = original_compare  # type: ignore[attr-defined]
        market_module.fetch_compare_stock = patched_compare

    if callable(original_valuation):
        def patched_valuation(symbol: str, *args: Any, **kwargs: Any):
            normalized = _normalize(symbol)
            value = original_valuation(symbol, *args, **kwargs)
            if not _is_korean_stock(normalized) or not isinstance(value, dict):
                return value
            try:
                quote = fetch_korean_stock_quote(normalized)
            except Exception as exc:
                print(f"[KoreaRealtime] valuation price fallback to Yahoo for {normalized}: {type(exc).__name__}: {exc}")
                return value

            merged = dict(value)
            merged["price"] = round(float(quote["price"]), 2)
            merged["currency"] = "KRW"
            merged["dataSource"] = f"{value.get('dataSource') or 'Market data'} + Naver realtime price"
            field_meta = dict(value.get("fieldMeta") or {})
            field_meta["price"] = {
                "source": quote.get("source") or "Naver Finance",
                "asOf": quote.get("asOf"),
                "period": "latest trading value",
                "method": "provider",
            }
            merged["fieldMeta"] = field_meta
            return merged

        patched_valuation.__chartview_korea_realtime__ = True  # type: ignore[attr-defined]
        patched_valuation.__wrapped__ = original_valuation  # type: ignore[attr-defined]
        market_module.fetch_valuation_snapshot = patched_valuation
