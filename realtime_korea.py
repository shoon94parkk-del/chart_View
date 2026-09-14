"""Reliable real-time Korean index quotes for Chart View.

Yahoo's Korean index feed can remain unchanged for long stretches during the
regular session.  For KOSPI/KOSDAQ we prefer Naver Finance's KRX/Koscom-backed
index endpoint and fall back to the existing Yahoo implementation on any error.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


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

    # Naver polling index values use two implied decimal places (527730 -> 5277.30).
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


def fetch_korean_index_quote(symbol: str) -> dict[str, Any]:
    symbol = str(symbol or "").strip().upper()
    if symbol not in INDEX_MAP:
        raise ValueError("unsupported Korean index")
    try:
        return _basic_index_quote(symbol)
    except Exception:
        return _polling_index_quote(symbol)


def install_patch(market_module: Any) -> None:
    """Patch only KOSPI/KOSDAQ; all other symbols keep the existing provider."""
    current = getattr(market_module, "fetch_quote_snapshot", None)
    if not callable(current) or getattr(current, "__chartview_korea_realtime__", False):
        return

    original: Callable[[str], dict[str, Any] | None] = current

    def patched(symbol: str):
        normalized = str(symbol or "").strip().upper()
        if normalized in INDEX_MAP:
            try:
                return fetch_korean_index_quote(normalized)
            except Exception as exc:
                print(f"[KoreaRealtime] Naver fallback to Yahoo for {normalized}: {type(exc).__name__}: {exc}")
        return original(symbol)

    patched.__chartview_korea_realtime__ = True  # type: ignore[attr-defined]
    patched.__wrapped__ = original  # type: ignore[attr-defined]
    market_module.fetch_quote_snapshot = patched
