"""Personalized watchlist news service.

Public response policy:
- Korean equities: NAVER API HUB News Search.
- North American equities: Finnhub Company News.
- Return headline/source/time/original URL only; never proxy article body or images.
- Support the full 20-symbol watchlist while bounding outbound provider concurrency.
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Query

router = APIRouter()

NEWS_CACHE: dict[str, dict] = {}
NEWS_CACHE_TTL = 300
MAX_SYMBOLS = 20
MAX_ITEMS_PER_SYMBOL = 6
PROVIDER_CONCURRENCY = 4
_PROVIDER_SEMAPHORE = threading.BoundedSemaphore(PROVIDER_CONCURRENCY)
_CACHE_LOCK = threading.Lock()

KR_EVENT_WORDS = (
    "실적", "영업이익", "매출", "수주", "계약", "인수", "합병", "증자", "감자",
    "배당", "자사주", "공시", "승인", "소송", "리콜", "목표가", "투자의견",
)
US_EVENT_WORDS = (
    "earnings", "revenue", "guidance", "acquire", "acquisition", "merger", "buyback",
    "dividend", "offering", "sec", "fda", "lawsuit", "recall", "forecast", "upgrade", "downgrade",
)
TAG_RE = re.compile(r"<[^>]+>")
SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.^=\-]{0,19}$")


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _host_label(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        return host or "원문"
    except Exception:
        return "원문"


def _is_kr(symbol: str) -> bool:
    return bool(re.search(r"\.(KS|KQ)$", symbol.upper()))


def _news_score(title: str, published_ts: float, market: str, name: str, symbol: str) -> float:
    now = time.time()
    age_hours = max(0.0, (now - published_ts) / 3600) if published_ts else 240.0
    score = max(0.0, 120.0 - age_hours * 2.0)
    lowered = title.lower()
    words = KR_EVENT_WORDS if market == "KR" else US_EVENT_WORDS
    score += sum(12 for word in words if word.lower() in lowered)
    if name and name.lower() in lowered:
        score += 20
    bare = symbol.split(".")[0].lower()
    if bare and bare in lowered:
        score += 10
    return round(score, 2)


def _dedupe(items: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[dict] = []
    for row in sorted(items, key=lambda x: (-float(x.get("score") or 0), -float(x.get("publishedTs") or 0))):
        url = str(row.get("url") or "").strip()
        title_key = re.sub(r"[^0-9a-z가-힣]+", "", str(row.get("title") or "").lower())[:120]
        if not url or not title_key or url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        out.append(row)
    return out


def _fetch_naver_news(symbol: str, name: str) -> dict:
    client_id = os.environ.get("NAVER_API_HUB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_API_HUB_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return {"items": [], "error": "not_configured", "provider": "naver-api-hub"}

    query = (name or symbol.split(".")[0]).strip()
    response = requests.get(
        "https://naverapihub.apigw.ntruss.com/search/v1/news",
        params={"query": query, "display": 20, "start": 1, "sort": "date", "format": "json"},
        headers={
            "X-NCP-APIGW-API-KEY-ID": client_id,
            "X-NCP-APIGW-API-KEY": client_secret,
            "User-Agent": "ChartView/40",
        },
        timeout=7,
    )
    response.raise_for_status()
    payload = response.json()
    items: list[dict] = []
    for raw in payload.get("items") or []:
        title = _clean_text(raw.get("title"))
        url = str(raw.get("originallink") or raw.get("link") or "").strip()
        if not title or not url:
            continue
        try:
            dt = parsedate_to_datetime(str(raw.get("pubDate") or ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            published_ts = dt.timestamp()
            published_at = dt.isoformat()
        except Exception:
            published_ts = 0.0
            published_at = None
        items.append({
            "symbol": symbol,
            "name": name or symbol,
            "market": "KR",
            "title": title,
            "source": _host_label(url),
            "publishedAt": published_at,
            "publishedTs": published_ts,
            "url": url,
            "provider": "NAVER API HUB",
            "score": _news_score(title, published_ts, "KR", name, symbol),
        })
    return {"items": _dedupe(items)[:MAX_ITEMS_PER_SYMBOL], "error": None, "provider": "naver-api-hub"}


def _fetch_finnhub_news(symbol: str, name: str) -> dict:
    token = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not token:
        return {"items": [], "error": "not_configured", "provider": "finnhub"}

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=4)
    response = requests.get(
        "https://finnhub.io/api/v1/company-news",
        params={"symbol": symbol, "from": start.isoformat(), "to": today.isoformat(), "token": token},
        headers={"User-Agent": "ChartView/40"},
        timeout=7,
    )
    response.raise_for_status()
    payload = response.json()
    items: list[dict] = []
    for raw in payload if isinstance(payload, list) else []:
        title = _clean_text(raw.get("headline"))
        url = str(raw.get("url") or "").strip()
        if not title or not url:
            continue
        published_ts = float(raw.get("datetime") or 0)
        published_at = datetime.fromtimestamp(published_ts, tz=timezone.utc).isoformat() if published_ts else None
        source = _clean_text(raw.get("source")) or _host_label(url)
        items.append({
            "symbol": symbol,
            "name": name or symbol,
            "market": "US",
            "title": title,
            "source": source,
            "publishedAt": published_at,
            "publishedTs": published_ts,
            "url": url,
            "provider": "Finnhub",
            "score": _news_score(title, published_ts, "US", name, symbol),
        })
    return {"items": _dedupe(items)[:MAX_ITEMS_PER_SYMBOL], "error": None, "provider": "finnhub"}


def _cached_fetch(symbol: str, name: str) -> dict:
    key = f"{symbol}|{name}".upper()
    with _CACHE_LOCK:
        cached = NEWS_CACHE.get(key)
        if cached and time.time() - float(cached.get("cachedAt") or 0) < NEWS_CACHE_TTL:
            return {**cached["data"], "cache": "hit"}

    try:
        with _PROVIDER_SEMAPHORE:
            data = _fetch_naver_news(symbol, name) if _is_kr(symbol) else _fetch_finnhub_news(symbol, name)
    except Exception as exc:
        data = {
            "items": [],
            "error": f"provider_error:{type(exc).__name__}",
            "provider": "naver-api-hub" if _is_kr(symbol) else "finnhub",
        }

    with _CACHE_LOCK:
        NEWS_CACHE[key] = {"cachedAt": time.time(), "data": data}
    return {**data, "cache": "miss"}


@router.get("/api/personalized-news")
async def personalized_news(
    tickers: str = Query(max_length=520),
    names: str = Query(default="", max_length=1400),
):
    raw_symbols = [part.strip().upper() for part in tickers.split(",") if part.strip()]
    symbols: list[str] = []
    for symbol in raw_symbols:
        if SYMBOL_RE.fullmatch(symbol) and symbol not in symbols:
            symbols.append(symbol)
    symbols = symbols[:MAX_SYMBOLS]
    raw_names = [part.strip() for part in names.split("|")] if names else []
    name_map = {symbol: (raw_names[i] if i < len(raw_names) else symbol) for i, symbol in enumerate(symbols)}

    if not symbols:
        return {
            "items": [], "groups": [], "errors": [], "requestedCount": 0,
            "providers": {"kr": "NAVER API HUB", "us": "Finnhub"},
            "displayPolicy": "headline-source-time-link-only",
        }

    fetched = await asyncio.gather(
        *[asyncio.to_thread(_cached_fetch, symbol, name_map[symbol]) for symbol in symbols],
        return_exceptions=True,
    )

    groups: list[dict] = []
    errors: list[dict] = []
    all_items: list[dict] = []
    for symbol, result in zip(symbols, fetched):
        if isinstance(result, Exception):
            result = {"items": [], "error": f"internal_error:{type(result).__name__}", "provider": "unknown"}
        rows = result.get("items") or []
        error = result.get("error")
        status = "error" if error else ("success" if rows else "no_news")
        groups.append({
            "symbol": symbol,
            "name": name_map[symbol],
            "market": "KR" if _is_kr(symbol) else "US",
            "items": rows,
            "status": status,
            "provider": result.get("provider"),
            "cache": result.get("cache"),
        })
        all_items.extend(rows)
        if error:
            errors.append({"symbol": symbol, "provider": result.get("provider"), "code": error})

    highlights = _dedupe(all_items)[:12]
    return {
        "items": highlights,
        "groups": groups,
        "errors": errors,
        "requestedCount": len(symbols),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "providers": {"kr": "NAVER API HUB", "us": "Finnhub Company News"},
        "providerConcurrency": PROVIDER_CONCURRENCY,
        "displayPolicy": "headline-source-time-link-only",
        "notice": "기사 본문과 이미지는 저장·재게시하지 않고 원문 링크로 연결합니다.",
    }
