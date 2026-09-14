"""Fast Korean news summaries for Chart View.

The endpoint prefers provider snippets for visible cards, translates the summary
with a small provider race, and only fetches article HTML when a usable snippet
is unavailable. This keeps the first three cards responsive on the free Render
instance while preserving article-body fallback behavior.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
import hashlib
import html
import ipaddress
import json
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

SUMMARY_CACHE: dict[str, dict] = {}
SUMMARY_CACHE_TTL = 60 * 60 * 6
SUMMARY_CACHE_VERSION = "v45-fastko1"
SUMMARY_FETCH_LIMIT = 1_200_000
SUMMARY_TEXT_LIMIT = 14_000
SUMMARY_CONCURRENCY = 3
_SUMMARY_LOCK = threading.Lock()
_SUMMARY_SEMAPHORE = threading.BoundedSemaphore(SUMMARY_CONCURRENCY)

_TRANSLATION_CACHE: dict[str, tuple[float, str]] = {}
_TRANSLATION_CACHE_TTL = 60 * 60 * 6
_TRANSLATION_LOCK = threading.Lock()
_TRANSLATE_URLS = (
    "https://translate.googleapis.com/translate_a/single",
    "https://translate.google.com/translate_a/single",
)
_TRANSLATE_FALLBACK_URL = "https://api.mymemory.translated.net/get"
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|(?<=다)\s+(?=[가-힣A-Z0-9])")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_KOREAN_RE = re.compile(r"[가-힣]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "after", "before", "will", "has", "have",
    "its", "are", "was", "were", "company", "companies", "stock", "shares", "news", "said", "says",
    "관련", "대한", "위한", "통해", "이번", "해당", "기업", "회사", "뉴스", "기사", "시장", "것으로", "있다고",
}
_SIGNAL_WORDS = (
    "earnings", "revenue", "profit", "loss", "eps", "guidance", "forecast", "margin", "contract", "order",
    "acquisition", "merger", "investment", "capex", "dividend", "buyback", "approval", "tariff", "lawsuit",
    "launch", "shipment", "production", "sales", "demand", "supply", "price", "target", "rating",
    "실적", "매출", "영업이익", "순이익", "손실", "가이던스", "전망", "수주", "계약", "인수", "합병",
    "투자", "증설", "배당", "자사주", "승인", "규제", "관세", "소송", "출시", "출하", "생산", "판매",
    "수요", "공급", "가격", "목표가", "투자의견",
)
_NOISE_WORDS = (
    "cookie", "cookies", "privacy policy", "terms of use", "subscribe", "subscription", "sign in", "sign up",
    "newsletter", "advertisement", "all rights reserved", "javascript", "브라우저", "쿠키", "개인정보처리방침",
    "구독", "로그인", "회원가입", "무단 전재", "재배포 금지",
)


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _has_korean(text: str) -> bool:
    ko = len(_KOREAN_RE.findall(text or ""))
    latin = len(_LATIN_RE.findall(text or ""))
    return ko >= 12 and ko >= latin * 0.22


def _looks_korean(text: str) -> bool:
    return len(_KOREAN_RE.findall(text or "")) >= 3


def _public_url_or_raise(raw_url: str) -> str:
    url = str(raw_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("unsupported_url")
    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".local"):
        raise ValueError("blocked_host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("dns_error") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError("blocked_address")
    return url


def _safe_fetch_html(raw_url: str) -> tuple[str, str]:
    current = _public_url_or_raise(raw_url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36 ChartView/45",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.7",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }
    for _ in range(4):
        current = _public_url_or_raise(current)
        response = requests.get(current, headers=headers, timeout=(2.5, 4.5), allow_redirects=False, stream=True)
        if response.status_code in _REDIRECT_CODES and response.headers.get("location"):
            current = urljoin(current, response.headers["location"])
            response.close()
            continue
        response.raise_for_status()
        content_type = str(response.headers.get("content-type") or "").lower()
        if content_type and "html" not in content_type and "xhtml" not in content_type:
            response.close()
            raise ValueError("not_html")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(32_768):
            if not chunk:
                continue
            total += len(chunk)
            if total > SUMMARY_FETCH_LIMIT:
                break
            chunks.append(chunk)
        encoding = response.encoding or "utf-8"
        response.close()
        raw = b"".join(chunks)
        try:
            return raw.decode(encoding, errors="replace"), current
        except LookupError:
            return raw.decode("utf-8", errors="replace"), current
    raise ValueError("redirect_limit")


def _jsonld_article_body(soup: BeautifulSoup) -> str:
    def walk(value: object) -> str:
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str) and len(_clean_text(body)) >= 180:
                return _clean_text(body)
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return ""

    for node in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = node.string or node.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            found = walk(json.loads(raw))
        except Exception:
            continue
        if found:
            return found[:SUMMARY_TEXT_LIMIT]
    return ""


def _extract_article(html_text: str) -> tuple[str, str]:
    soup = BeautifulSoup(html_text or "", "lxml")
    page_description = ""
    for attrs in ({"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}):
        node = soup.find("meta", attrs=attrs)
        value = _clean_text(node.get("content")) if node else ""
        if len(value) > len(page_description):
            page_description = value
    body = _jsonld_article_body(soup)
    if body:
        return body, page_description
    for tag in soup(["script", "style", "noscript", "nav", "footer", "aside", "form", "svg"]):
        tag.decompose()
    best = ""
    for root in (soup.find("article"), soup.find("main"), soup.body):
        if not root:
            continue
        parts: list[str] = []
        for p in root.find_all("p"):
            text = _clean_text(p.get_text(" ", strip=True))
            low = text.lower()
            if len(text) < 35 or any(noise in low for noise in _NOISE_WORDS):
                continue
            parts.append(text)
            if sum(len(x) for x in parts) >= SUMMARY_TEXT_LIMIT:
                break
        candidate = " ".join(parts)
        if len(candidate) > len(best):
            best = candidate
        if len(best) >= 900:
            break
    return best[:SUMMARY_TEXT_LIMIT], page_description


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "") if token.lower() not in _STOPWORDS}


def _split_sentences(text: str) -> list[str]:
    rows = [_clean_text(row) for row in _SENTENCE_SPLIT_RE.split(_clean_text(text))]
    return [row for row in rows if 28 <= len(row) <= 520 and not any(noise in row.lower() for noise in _NOISE_WORDS)]


def _sentence_score(sentence: str, index: int, title_tokens: set[str]) -> float:
    lower = sentence.lower()
    sentence_tokens = _tokens(sentence)
    overlap = len(sentence_tokens & title_tokens)
    signals = sum(1 for word in _SIGNAL_WORDS if word in lower)
    number_bonus = 2.2 if re.search(r"\d", sentence) else 0.0
    early_bonus = max(0.0, 4.5 - index * 0.35)
    length_bonus = 1.5 if 55 <= len(sentence) <= 300 else 0.2
    return overlap * 3.2 + signals * 1.7 + number_bonus + early_bonus + length_bonus


def _pick_summary_sentences(text: str, title: str, limit: int = 2) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    title_tokens = _tokens(title)
    ranked = sorted(enumerate(sentences), key=lambda pair: (-_sentence_score(pair[1], pair[0], title_tokens), pair[0]))
    chosen: list[tuple[int, str]] = []
    for index, sentence in ranked:
        tokens = _tokens(sentence)
        if any((tokens | _tokens(prior)) and len(tokens & _tokens(prior)) / len(tokens | _tokens(prior)) > 0.62 for _, prior in chosen):
            continue
        chosen.append((index, sentence))
        if len(chosen) >= limit:
            break
    chosen.sort(key=lambda pair: pair[0])
    return " ".join(sentence for _, sentence in chosen)


def _google_translate_once(endpoint: str, source: str) -> str:
    response = requests.get(
        endpoint,
        params={"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": source[:2400]},
        headers={"User-Agent": "Mozilla/5.0 ChartView/45"},
        timeout=(2, 4),
    )
    response.raise_for_status()
    payload = response.json()
    translated = _clean_text("".join(str(row[0] or "") for row in (payload[0] or []) if isinstance(row, list) and row))
    if not translated or not _looks_korean(translated):
        raise ValueError("translation_not_korean")
    return translated


def _fallback_translate(source: str) -> str:
    response = requests.get(
        _TRANSLATE_FALLBACK_URL,
        params={"q": source[:480], "langpair": "en|ko"},
        headers={"User-Agent": "ChartView/45"},
        timeout=(2, 4),
    )
    response.raise_for_status()
    payload = response.json()
    translated = _clean_text((payload.get("responseData") or {}).get("translatedText"))
    if not translated or not _looks_korean(translated):
        raise ValueError("fallback_translation_not_korean")
    return translated


def _translation_cache_get(source: str) -> str:
    key = hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()
    with _TRANSLATION_LOCK:
        row = _TRANSLATION_CACHE.get(key)
        if row and time.time() - row[0] < _TRANSLATION_CACHE_TTL:
            return row[1]
    return ""


def _translation_cache_put(source: str, translated: str) -> None:
    key = hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()
    with _TRANSLATION_LOCK:
        _TRANSLATION_CACHE[key] = (time.time(), translated)
        if len(_TRANSLATION_CACHE) > 1600:
            oldest = sorted(_TRANSLATION_CACHE.items(), key=lambda pair: pair[1][0])[:300]
            for old_key, _ in oldest:
                _TRANSLATION_CACHE.pop(old_key, None)


def _translate_ko(text: str) -> tuple[str, bool]:
    source = _clean_text(text)
    if not source:
        return "", False
    if _has_korean(source):
        return source, False
    cached = _translation_cache_get(source)
    if cached:
        return cached, True

    executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cv-translate")
    futures = [executor.submit(_google_translate_once, endpoint, source) for endpoint in _TRANSLATE_URLS]
    futures.append(executor.submit(_fallback_translate, source))
    errors: list[str] = []
    try:
        try:
            for future in as_completed(futures, timeout=4.8):
                try:
                    translated = future.result()
                    if translated and _looks_korean(translated):
                        _translation_cache_put(source, translated)
                        return translated, True
                except Exception as exc:
                    errors.append(type(exc).__name__)
        except FuturesTimeoutError:
            errors.append("Timeout")
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    raise RuntimeError("translation_failed:" + ",".join(errors[:3]))


def _trim_summary(text: str, limit: int = 360) -> str:
    value = _clean_text(text)
    if len(value) <= limit:
        return value
    clipped = value[:limit]
    for marker in ("다. ", ". ", "요. "):
        cut = clipped.rfind(marker)
        if cut >= int(limit * 0.55):
            return clipped[: cut + len(marker)].strip()
    cut = max(clipped.rfind(" "), clipped.rfind(","), clipped.rfind("·"))
    return (clipped[:cut] if cut >= int(limit * 0.7) else clipped).rstrip(" ,·") + "…"


def _cache_key(url: str, title: str, snippet: str) -> str:
    raw = f"{SUMMARY_CACHE_VERSION}\n{url}\n{title}\n{snippet[:800]}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _build_summary(url: str, title: str, snippet: str) -> dict:
    key = _cache_key(url, title, snippet)
    with _SUMMARY_LOCK:
        cached = SUMMARY_CACHE.get(key)
        if cached and time.time() - float(cached.get("cachedAt") or 0) < SUMMARY_CACHE_TTL:
            return {**cached["data"], "cache": "hit"}

    with _SUMMARY_SEMAPHORE:
        clean_title = _clean_text(title)
        clean_snippet = _clean_text(snippet)
        article_text = ""
        page_description = ""
        fetch_error = None

        # Fast path: providers already give a useful summary seed. Do not make the
        # user wait for a publisher page fetch before Korean translation starts.
        if len(clean_snippet) >= 60:
            basis, source_text = "provider_snippet", clean_snippet
        else:
            try:
                fetched_html, _ = _safe_fetch_html(url)
                article_text, page_description = _extract_article(fetched_html)
            except Exception as exc:
                fetch_error = type(exc).__name__

            basis = "headline_only"
            source_text = ""
            if len(article_text) >= 180:
                basis = "article_body"
                source_text = _pick_summary_sentences(article_text, clean_title, limit=2)
            if not source_text and len(page_description) >= 70:
                basis, source_text = "page_description", page_description
            if not source_text and len(clean_snippet) >= 20:
                basis = "title_snippet_fallback"
                source_text = f"{clean_title}. {clean_snippet}" if clean_title else clean_snippet
            if not source_text and clean_title:
                basis, source_text = "headline_only", clean_title

        translated = False
        translation_error = None
        title_ko = clean_title or "기사"
        summary_ko = ""

        if basis == "headline_only" and clean_title:
            try:
                title_ko, title_translated = _translate_ko(clean_title)
                translated = bool(title_translated)
                summary_ko = f"제목 기준 · {title_ko}" if _looks_korean(title_ko) else ""
            except Exception:
                summary_ko = "기사 제목을 바탕으로 한 한국어 번역이 일시적으로 지연되고 있습니다. 원문 보기에서 내용을 확인해 주세요."
                translation_error = "summary_translation_failed"
        elif source_text:
            # Translate headline and summary concurrently; the summary is the
            # priority, but this preserves the Korean-title UX when available.
            pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cv-summary")
            title_future = pool.submit(_translate_ko, clean_title) if clean_title and not _has_korean(clean_title) else None
            summary_future = pool.submit(_translate_ko, source_text)
            title_translated = False
            body_translated = False
            try:
                try:
                    summary_ko, body_translated = summary_future.result(timeout=5.4)
                except Exception:
                    summary_ko = source_text if _has_korean(source_text) else ""
                if title_future:
                    try:
                        title_ko, title_translated = title_future.result(timeout=0.35 if summary_ko else 1.0)
                    except Exception:
                        title_ko = clean_title or "기사"
                translated = bool(title_translated or body_translated)
            finally:
                if title_future:
                    title_future.cancel()
                summary_future.cancel()
                pool.shutdown(wait=False, cancel_futures=True)

            if not summary_ko or (not _has_korean(summary_ko) and not _looks_korean(summary_ko)):
                if _looks_korean(title_ko):
                    summary_ko = f"핵심 제목 · {title_ko}"
                    translation_error = "summary_translation_title_fallback"
                else:
                    summary_ko = "기사 요약은 생성됐지만 한국어 번역이 일시적으로 지연되고 있습니다. 잠시 후 새로고침해 주세요."
                    translation_error = "summary_translation_failed"
        else:
            summary_ko = "기사 제목과 요약문이 제공되지 않았습니다. 원문에서 내용을 확인해 주세요."

        labels = {
            "article_body": "본문 기반",
            "page_description": "본문 설명 기반",
            "provider_snippet": "기사 요약문 기반",
            "title_snippet_fallback": "제목·요약문 기반",
            "headline_only": "제목 기반",
        }
        result = {
            "titleKo": _trim_summary(title_ko, 180),
            "summary": _trim_summary(summary_ko, 360),
            "basis": basis,
            "basisLabel": labels[basis],
            "translated": translated,
            "fetchError": fetch_error,
            "translationError": translation_error,
            "generatedAt": time.time(),
            "notice": "기사 본문은 저장·재게시하지 않고 요약 결과만 임시 캐시합니다.",
        }

    if translation_error != "summary_translation_failed":
        with _SUMMARY_LOCK:
            SUMMARY_CACHE[key] = {"cachedAt": time.time(), "data": result}
            if len(SUMMARY_CACHE) > 1200:
                oldest = sorted(SUMMARY_CACHE.items(), key=lambda pair: float(pair[1].get("cachedAt") or 0))[:200]
                for old_key, _ in oldest:
                    SUMMARY_CACHE.pop(old_key, None)
    return {**result, "cache": "miss"}


@router.get("/api/news-summary")
async def news_summary(
    url: str = Query(max_length=2048),
    title: str = Query(default="", max_length=600),
    snippet: str = Query(default="", max_length=1200),
):
    try:
        _public_url_or_raise(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="지원하지 않는 기사 주소입니다.") from exc
    try:
        return await asyncio.to_thread(_build_summary, url, _clean_text(title), _clean_text(snippet))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"기사 요약 생성 실패: {type(exc).__name__}") from exc
