"""Personalized watchlist news service.

Public response policy:
- Korean equities: NAVER API HUB News Search.
- North American equities: Finnhub Company News.
- Return headline/source/time/original URL plus a short provider summary seed; never proxy article body or images.
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

MIN_HIGHLIGHT_INVESTMENT_SCORE = 18.0

# Home TOP news is investor-first: market-moving business events outrank simple company mentions.
KR_INVESTMENT_CATEGORIES = (
    ("earnings", 50, ("실적", "영업이익", "영업손실", "순이익", "순손실", "매출", "흑자전환", "적자전환", "어닝", "가이던스", "실적 전망")),
    ("orders", 42, ("수주", "공급계약", "계약 체결", "납품", "고객사", "발주", "수주잔고")),
    ("capital", 38, ("배당", "자사주", "증자", "감자", "유상증자", "무상증자", "회사채", "차입", "신용등급", "분할", "상장")),
    ("strategy", 34, ("인수", "합병", "m&a", "매각", "지분 인수", "투자", "증설", "감산", "생산능력", "capex", "공장", "라인 가동")),
    ("technology", 30, ("파운드리", "hbm", "dram", "낸드", "반도체", "2나노", "3나노", "공정", "수율", "양산", "출하", "신제품", "출시", "점유율")),
    ("analyst", 28, ("목표가", "목표주가", "투자의견", "매수", "매도", "상향", "하향", "컨센서스")),
    ("market", 26, ("주가", "급등", "급락", "외국인", "기관", "수급", "공매도", "거래량")),
    ("policy", 28, ("공시", "승인", "규제", "관세", "보조금", "소송", "리콜", "제재", "조사", "과징금")),
    ("pricing", 26, ("가격 인상", "가격 인하", "판가", "가격 상승", "가격 하락", "판매량", "출하량")),
)
US_INVESTMENT_CATEGORIES = (
    ("earnings", 50, ("earnings", "revenue", "profit", "loss", "eps", "guidance", "forecast", "outlook", "margin")),
    ("orders", 42, ("contract", "order", "supply deal", "customer", "backlog", "shipment")),
    ("capital", 38, ("dividend", "buyback", "offering", "debt", "bond", "credit rating", "split", "ipo")),
    ("strategy", 34, ("acquire", "acquisition", "merger", "m&a", "sell stake", "investment", "capex", "capacity", "factory", "fab")),
    ("technology", 30, ("foundry", "hbm", "dram", "nand", "semiconductor", "2nm", "3nm", "yield", "mass production", "launch", "market share")),
    ("analyst", 28, ("price target", "upgrade", "downgrade", "rating", "buy", "sell", "outperform", "underperform")),
    ("market", 26, ("shares", "stock", "surge", "plunge", "short interest", "volume")),
    ("policy", 28, ("sec", "fda", "approval", "regulation", "tariff", "subsidy", "lawsuit", "recall", "probe", "fine")),
    ("pricing", 26, ("price increase", "price cut", "pricing", "unit sales", "shipments")),
)
KR_LOW_VALUE_WORDS = (
    "어린이", "청소년", "교육", "사용법", "캠페인", "봉사", "기부", "사회공헌", "후원",
    "공모전", "체험", "축제", "문화행사", "지역사회", "장학", "취약계층", "홍보대사", "나눔",
)
US_LOW_VALUE_WORDS = (
    "children", "students", "education", "how to use", "campaign", "volunteer", "donation",
    "charity", "sponsorship", "contest", "festival", "community event", "scholarship", "ambassador",
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


def _investment_relevance(title: str, context: str, market: str) -> tuple[float, list[str]]:
    text = f"{title} {context}".lower()
    categories = KR_INVESTMENT_CATEGORIES if market == "KR" else US_INVESTMENT_CATEGORIES
    low_value_words = KR_LOW_VALUE_WORDS if market == "KR" else US_LOW_VALUE_WORDS

    score = 0.0
    tags: list[str] = []
    for tag, weight, words in categories:
        if any(word.lower() in text for word in words):
            score += float(weight)
            tags.append(tag)

    low_hits = sum(1 for word in low_value_words if word.lower() in text)
    if low_hits:
        # CSR/education/event stories should not become Home TOP news merely because they are fresh.
        score -= (60.0 + max(0, low_hits - 1) * 12.0) if not tags else low_hits * 22.0

    if tags and re.search(r"\d+(?:\.\d+)?\s*(?:%|조|억|만|달러|원|billion|million|bn|mn)", text, re.I):
        score += 8.0
    return round(score, 2), tags


def _relation_meta(title: str, context: str, name: str, symbol: str) -> tuple[str, str]:
    aliases = {"NVDA": ("nvidia", "엔비디아"), "AAPL": ("apple", "애플"), "MSFT": ("microsoft", "마이크로소프트"), "005930.KS": ("samsung", "삼성전자"), "000660.KS": ("sk hynix", "sk하이닉스")}
    for alias in aliases.get(symbol.upper(), ()):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", f"{title} {context}".lower()):
            return "direct", "기사 제목·요약에 기업명 확인"
    title_l = title.lower()
    context_l = context.lower()
    name_l = (name or "").strip().lower()
    bare = symbol.split(".")[0].lower()
    title_hit = bool(name_l and name_l in title_l) or bool(len(bare) >= 2 and re.search(rf"(?<![a-z0-9]){re.escape(bare)}(?![a-z0-9])", title_l))
    context_hit = bool(name_l and name_l in context_l) or bool(len(bare) >= 2 and re.search(rf"(?<![a-z0-9]){re.escape(bare)}(?![a-z0-9])", context_l))
    if title_hit:
        return "direct", "제목에 기업명·티커 확인"
    if context_hit:
        return "direct", "제공처 기사 요약에 기업명·티커 확인"
    sectors = {"NVDA": ("hbm", "gpu", "반도체", "semiconductor"), "005930.KS": ("hbm", "dram", "반도체", "semiconductor"), "000660.KS": ("hbm", "dram", "반도체", "semiconductor"), "AAPL": ("smartphone", "스마트폰", "iphone", "아이폰")}
    for term in sectors.get(symbol.upper(), ()):
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", f"{title_l} {context_l}"):
            return "related", f"기사 제목·요약에 관련 업종 키워드 확인: {term}"
    return "unverified", "기업·업종 관련 근거 미확인"


def _news_score(title: str, published_ts: float, market: str, name: str, symbol: str, context: str = "") -> float:
    now = time.time()
    age_hours = max(0.0, (now - published_ts) / 3600) if published_ts else 240.0
    # Recency matters, but it must never dominate actual investment relevance.
    recency_score = max(0.0, 30.0 - age_hours * 0.625)
    investment_score, _ = _investment_relevance(title, context, market)
    score = investment_score + recency_score
    lowered = title.lower()
    if name and name.lower() in lowered:
        score += 10.0
    bare = symbol.split(".")[0].lower()
    if bare and bare in lowered:
        score += 6.0
    if investment_score < MIN_HIGHLIGHT_INVESTMENT_SCORE:
        score -= 35.0
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


def _balanced_highlights(items: list[dict], limit: int = 12) -> list[dict]:
    """Investor-first Home highlights with ticker diversity; low-value company mentions are omitted."""
    ranked = _dedupe(items)
    if not ranked or limit <= 0:
        return []

    qualified = [
        row for row in ranked
        if "investmentRelevant" not in row or bool(row.get("investmentRelevant"))
    ]
    if not qualified:
        return []

    first_by_symbol: dict[str, dict] = {}
    for row in qualified:
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in first_by_symbol:
            first_by_symbol[symbol] = row

    primary = sorted(
        first_by_symbol.values(),
        key=lambda x: (-float(x.get("score") or 0), -float(x.get("publishedTs") or 0)),
    )
    chosen = primary[:limit]
    chosen_ids = {(str(row.get("url") or ""), str(row.get("title") or "")) for row in chosen}
    if len(chosen) < limit:
        for row in qualified:
            identity = (str(row.get("url") or ""), str(row.get("title") or ""))
            if identity in chosen_ids:
                continue
            chosen.append(row)
            chosen_ids.add(identity)
            if len(chosen) >= limit:
                break
    return chosen


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
        context = _clean_text(raw.get("description"))
        investment_score, investment_tags = _investment_relevance(title, context, "KR")
        relation_type, relation_basis = _relation_meta(title, context, name, symbol)
        if relation_type == "unverified":
            continue
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
            "score": _news_score(title, published_ts, "KR", name, symbol, context),
            "investmentScore": investment_score,
            "investmentRelevant": investment_score >= MIN_HIGHLIGHT_INVESTMENT_SCORE,
            "investmentTags": investment_tags,
            "relationType": relation_type,
            "relationBasis": relation_basis,
            "summarySeed": context[:700],
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
        context = _clean_text(raw.get("summary"))
        investment_score, investment_tags = _investment_relevance(title, context, "US")
        relation_type, relation_basis = _relation_meta(title, context, name, symbol)
        if relation_type == "unverified":
            continue
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
            "score": _news_score(title, published_ts, "US", name, symbol, context),
            "investmentScore": investment_score,
            "investmentRelevant": investment_score >= MIN_HIGHLIGHT_INVESTMENT_SCORE,
            "investmentTags": investment_tags,
            "relationType": relation_type,
            "relationBasis": relation_basis,
            "summarySeed": context[:700],
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
            "displayPolicy": "headline-source-time-link-summary-seed",
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

    highlights = _balanced_highlights(all_items, 12)
    return {
        "items": highlights,
        "groups": groups,
        "errors": errors,
        "requestedCount": len(symbols),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "providers": {"kr": "NAVER API HUB", "us": "Finnhub Company News"},
        "providerConcurrency": PROVIDER_CONCURRENCY,
        "displayPolicy": "headline-source-time-link-summary-seed",
        "selectionPolicy": "investor-first-diverse-v41.6",
        "notice": "기사 본문·이미지는 저장하거나 재게시하지 않으며, 화면 요약은 원문을 일시적으로 읽어 한국어 요약만 생성합니다.",
    }
