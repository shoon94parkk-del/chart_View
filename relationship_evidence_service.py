"""Evidence-backed direct company relationship service for IDEA LAB.

Only surfaces a direct relationship when a recent company news item:
1) is already verified as directly about the subject company,
2) contains a strong commercial relationship keyword, and
3) explicitly names another KRX-listed company in the same evidence text.

Industry adjacency remains a separate UI concept and is never upgraded to "direct".
"""
from __future__ import annotations

import json
import re
import time
import threading
from pathlib import Path

from fastapi import APIRouter, Query
import asyncio

from news_service_v37 import _cached_fetch

router = APIRouter()

COMPANY_CONTEXT_PATH = Path("static/data/company_context.json")
CACHE_TTL = 6 * 3600
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_COMPANIES: tuple[float, list[dict]] = (0.0, [])

RELATION_PATTERNS = (
    ("공급·납품", re.compile(r"공급계약|단일판매.?공급계약|납품|공급사|벤더|vendor", re.I)),
    ("수주·발주", re.compile(r"수주|발주|수주잔고", re.I)),
    ("고객·채택", re.compile(r"고객사|주요.?고객|채택|탑재|적용.?확대", re.I)),
    ("계약", re.compile(r"계약.?체결|장기.?계약|전략적.?계약", re.I)),
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|[\n\r]+")
GENERIC_NAMES = {
    "대상", "우리", "미래", "보성", "한솔", "삼성", "한화", "현대", "동양", "동아", "대성",
}


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _load_companies() -> list[dict]:
    global _COMPANIES
    try:
        mtime = COMPANY_CONTEXT_PATH.stat().st_mtime
    except OSError:
        return []
    with _LOCK:
        if _COMPANIES[1] and _COMPANIES[0] == mtime:
            return _COMPANIES[1]
    try:
        payload = json.loads(COMPANY_CONTEXT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = []
    for raw in payload.get("companies") or []:
        name = _clean(raw.get("name"))
        symbol = _clean(raw.get("symbol")).upper()
        if not name or not symbol or len(name) < 3 or name in GENERIC_NAMES:
            continue
        rows.append({"name": name, "symbol": symbol})
    rows.sort(key=lambda x: len(x["name"]), reverse=True)
    with _LOCK:
        _COMPANIES = (mtime, rows)
    return rows


def _relation_label(text: str) -> str | None:
    for label, pattern in RELATION_PATTERNS:
        if pattern.search(text or ""):
            return label
    return None


def _company_mentioned(name: str, text: str) -> bool:
    if not name or not text:
        return False
    if re.fullmatch(r"[A-Za-z0-9&.\-]+", name):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.I))
    return name in text


def _counterparties_in_evidence(text: str, subject_name: str, subject_symbol: str, companies: list[dict]) -> list[dict]:
    found = []
    subject_name = _clean(subject_name)
    subject_symbol = _clean(subject_symbol).upper()
    for company in companies:
        if company["symbol"] == subject_symbol or company["name"] == subject_name:
            continue
        if _company_mentioned(company["name"], text):
            found.append(company)
            if len(found) >= 8:
                break
    return found


def extract_direct_relations(subject_name: str, subject_symbol: str, news_items: list[dict], companies: list[dict] | None = None) -> list[dict]:
    companies = companies if companies is not None else _load_companies()
    relations: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for item in news_items or []:
        if item.get("relationType") != "direct":
            continue
        title = _clean(item.get("title"))
        context = _clean(item.get("summarySeed"))
        full_text = f"{title}. {context}".strip()
        if not full_text:
            continue

        evidence_chunks = [title] + [chunk for chunk in SENTENCE_SPLIT_RE.split(context) if chunk]
        candidates = _counterparties_in_evidence(full_text, subject_name, subject_symbol, companies)
        for counterparty in candidates:
            matched_label = None
            matched_chunk = None
            for chunk in evidence_chunks:
                if not _company_mentioned(counterparty["name"], chunk):
                    continue
                label = _relation_label(chunk)
                if label:
                    matched_label = label
                    matched_chunk = chunk
                    break
            if not matched_label:
                continue
            key = (counterparty["symbol"], str(item.get("url") or ""))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            relations.append({
                "counterpartyName": counterparty["name"],
                "counterpartySymbol": counterparty["symbol"],
                "relationLabel": matched_label,
                "headline": title,
                "source": _clean(item.get("source")) or "뉴스",
                "publishedAt": item.get("publishedAt"),
                "url": str(item.get("url") or ""),
                "basis": "기사 제목·요약에 상장사명과 직접 거래/고객 키워드가 함께 확인됨",
                "evidencePreview": _clean(matched_chunk)[:180],
            })

    relations.sort(key=lambda x: str(x.get("publishedAt") or ""), reverse=True)
    # One freshest evidence item per counterparty keeps the UI compact.
    compact: list[dict] = []
    used: set[str] = set()
    for row in relations:
        symbol = row["counterpartySymbol"]
        if symbol in used:
            continue
        used.add(symbol)
        compact.append(row)
        if len(compact) >= 4:
            break
    return compact


def fetch_relationship_evidence(ticker: str, name: str) -> dict:
    symbol = _clean(ticker).upper()
    subject_name = _clean(name)
    if not re.fullmatch(r"\d{6}\.(KS|KQ)", symbol):
        return {"ticker": symbol, "available": False, "relations": [], "reason": "korean_ticker_required"}

    key = f"{symbol}|{subject_name}"
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return {**cached[1], "cache": "hit"}

    fetched = _cached_fetch(symbol, subject_name)
    items = fetched.get("items") or []
    relations = extract_direct_relations(subject_name, symbol, items)
    result = {
        "ticker": symbol,
        "name": subject_name,
        "available": bool(relations),
        "relations": relations,
        "checkedNewsCount": len(items),
        "provider": fetched.get("provider"),
        "reason": None if relations else ("news_provider_unavailable" if fetched.get("error") else "no_evidence_backed_direct_relation"),
        "evidencePolicy": "named-listed-counterparty + strong commercial keyword in the same news evidence chunk",
    }
    with _LOCK:
        _CACHE[key] = (time.time(), result)
    return {**result, "cache": "miss"}


@router.get("/api/relationship-evidence")
async def relationship_evidence(
    ticker: str = Query(..., min_length=9, max_length=12),
    name: str = Query("", max_length=80),
):
    return await asyncio.to_thread(fetch_relationship_evidence, ticker, name)
