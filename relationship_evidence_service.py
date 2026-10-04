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
RESPONSE_TIMEOUT = 9
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_COMPANIES: tuple[float, list[dict]] = (0.0, [])

RELATION_PATTERNS = (
    ("공급·납품", re.compile(r"공급계약|납품계약|납품(?:했|한다|중|하기로|을|를)|공급사로\s*(?:선정|지정)", re.I)),
    ("수주·발주", re.compile(r"수주\s*계약|발주(?:했|한다|계약|를\s*받)", re.I)),
    ("고객·채택", re.compile(r"고객사로\s*(?:확보|선정|등록)|(?:제품|부품|장비).{0,15}채택", re.I)),
    ("계약", re.compile(r"계약(?:을|을\s*새로)?\s*(?:체결|맺|따냈|공시)", re.I)),
)
CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|[\n\r]+|[▲▶◆]|\s+-\s+(?=[가-힣A-Za-z])")
ROUNDUP_RE = re.compile(r"오늘의\s*특징주|특징주|주식마감|기업\s*공시|주요\s*공시|경제\s*브리핑|모닝.{0,10}브리핑|증시\s*마감|코스피|코스닥|상한가|종목\s*뉴스|뉴스톡톡|뉴스인사이드", re.I)
SPECULATIVE_RE = re.compile(r"가능성|기대감?|전망|추정|관측|소문|거론|후보|예상|검토|논의", re.I)
ENDED_RELATION_RE = re.compile(
    r"계약(?:을|이|의)?\s*(?:해지|종료)|"
    r"공급(?:을|이|의)?\s*중단|"
    r"납품(?:을|이|의)?\s*중단|"
    r"거래(?:를|가|의)?\s*중단|"
    r"취소|무산",
    re.I,
)
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
    # Korean particles may follow an issuer name, but another Hangul syllable
    # usually means the name is only a prefix of a different company.
    return bool(re.search(
        rf"(?<![가-힣A-Za-z0-9]){re.escape(name)}(?=$|[^가-힣A-Za-z0-9]|[은는이가을를와과에의로도만])",
        text,
    ))


def _unshadowed_company_mentioned(name: str, text: str, companies: list[dict]) -> bool:
    # A short listed name can occur inside another issuer's name (e.g. 이닉스
    # inside SK하이닉스, HD현대 inside HD현대중공업).
    if not _company_mentioned(name, text):
        return False
    visible = text
    for company in companies:
        other = company["name"]
        if other != name and len(other) > len(name) and name in other:
            visible = visible.replace(other, " ")
    return _company_mentioned(name, visible)


def _counterparties_in_evidence(text: str, subject_name: str, subject_symbol: str, companies: list[dict]) -> list[dict]:
    found = []
    subject_name = _clean(subject_name)
    subject_symbol = _clean(subject_symbol).upper()
    for company in companies:
        if company["symbol"] == subject_symbol or company["name"] == subject_name:
            continue
        if _unshadowed_company_mentioned(company["name"], text, companies):
            found.append(company)
            if len(found) >= 8:
                break
    return found


def _explicit_pair_role(text: str, subject: str, counterparty: str) -> bool:
    """Require a named actor and named contract target, in either direction.

    A list of co-suppliers followed by a third company's contract is not a
    transaction between those suppliers. Ambiguous phrasing stays omitted.
    """
    for actor, target in ((subject, counterparty), (counterparty, subject)):
        for actor_match in re.finditer(re.escape(actor), text):
            tail = text[actor_match.end():]
            target_match = re.search(re.escape(target), tail)
            if not target_match or target_match.start() > 100:
                continue
            between = tail[:target_match.start()]
            if re.match(r"\s*(?:와|과|및|·|&|and\b)", between, re.I):
                continue
            after_target = tail[target_match.end():]
            role = re.match(r"(?:에게서|로부터|에게|와|과|에|를|을)(?:의)?", after_target)
            if not role and re.match(r"\s*(?:은|는|이|가)(?:\s|$)", between):
                # Explicit actor, several named customers: A는 B 및 C와 계약.
                role = re.match(
                    r"\s*(?:및|,|·)\s*[가-힣A-Za-z0-9&.\-]{2,30}"
                    r"(?:\s*(?:및|,|·)\s*[가-힣A-Za-z0-9&.\-]{2,30}){0,2}"
                    r"(?:에게서|로부터|에게|와|과|에|를|을)(?:의)?", after_target
                )
            if not role:
                continue
            if re.match(r"\s*(?:같은|함께|동반|동일|비슷|경쟁)", after_target[role.end():]):
                continue
            if _relation_label(tail[target_match.start():]):
                return True
    return False


def extract_direct_relations(subject_name: str, subject_symbol: str, news_items: list[dict], companies: list[dict] | None = None) -> list[dict]:
    companies = companies if companies is not None else _load_companies()
    relations: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for item in news_items or []:
        if item.get("relationType") != "direct":
            continue
        title = _clean(item.get("title"))
        context = _clean(item.get("summarySeed"))
        if ROUNDUP_RE.search(title):
            continue
        full_text = f"{title}. {context}".strip()
        if not full_text:
            continue

        dedicated_title = title.find(subject_name) >= 0 and title.find(subject_name) <= 15
        evidence_chunks = [title] + [chunk for chunk in CLAUSE_SPLIT_RE.split(context) if chunk]
        candidates = _counterparties_in_evidence(full_text, subject_name, subject_symbol, companies)
        for counterparty in candidates:
            matched_label = None
            matched_chunk = None
            for chunk in evidence_chunks:
                if not _unshadowed_company_mentioned(counterparty["name"], chunk, companies):
                    continue
                if SPECULATIVE_RE.search(chunk) or ENDED_RELATION_RE.search(chunk):
                    continue
                label = _relation_label(chunk)
                # A summary may omit the article's subject, but only a dedicated
                # single-company headline can supply that missing context.
                subject_in_chunk = _company_mentioned(subject_name, chunk)
                if label and (subject_in_chunk or dedicated_title):
                    if subject_in_chunk and not _explicit_pair_role(chunk, subject_name, counterparty["name"]):
                        continue
                    if subject_in_chunk and abs(chunk.find(subject_name) - chunk.find(counterparty["name"])) > 100:
                        continue
                    if not subject_in_chunk and not re.search(
                        rf"{re.escape(counterparty['name'])}(?:와|과|에|에게|로부터|를|을)", chunk
                    ):
                        continue
                    if len(chunk) > 180 and not subject_in_chunk:
                        continue
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
                "basis": "단일 기업 기사에서 두 회사의 구체적 계약·납품 표현 확인",
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


def fetch_relationship_evidence(ticker: str, name: str, *, force: bool = False) -> dict:
    symbol = _clean(ticker).upper()
    subject_name = _clean(name)
    if not re.fullmatch(r"\d{6}\.(KS|KQ)", symbol):
        return {"ticker": symbol, "available": False, "relations": [], "reason": "korean_ticker_required"}

    key = f"{symbol}|{subject_name}"
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and not force and time.time() - cached[0] < CACHE_TTL:
            return {**cached[1], "cache": "hit"}

    fetched = _cached_fetch(symbol, subject_name, force=True) if force else _cached_fetch(symbol, subject_name)
    items = list(fetched.get("items") or [])
    relations = extract_direct_relations(subject_name, symbol, items)

    result = {
        "ticker": symbol,
        "name": subject_name,
        "available": bool(relations),
        "relations": relations,
        "checkedNewsCount": len(items),
        "targetedSearchCount": 0,
        "provider": fetched.get("provider"),
        "searchMode": "general",
        "reason": None if relations else ("news_provider_unavailable" if fetched.get("error") else "no_evidence_backed_direct_relation"),
        "evidencePolicy": "single-company article + explicit named actor/contract target roles + concrete contract/delivery wording in one clause; co-suppliers, roundup, speculative and ended relationships excluded",
    }
    with _LOCK:
        _CACHE[key] = (time.time(), result)
    return {**result, "cache": "miss"}


@router.get("/api/relationship-evidence")
async def relationship_evidence(
    ticker: str = Query(..., min_length=9, max_length=12),
    name: str = Query("", max_length=80),
    force: bool = False,
):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fetch_relationship_evidence, ticker, name, force=True) if force else asyncio.to_thread(fetch_relationship_evidence, ticker, name),
            timeout=RESPONSE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return {
            "ticker": _clean(ticker).upper(),
            "name": _clean(name),
            "available": False,
            "relations": [],
            "reason": "provider_timeout",
            "searchMode": "general",
        }
