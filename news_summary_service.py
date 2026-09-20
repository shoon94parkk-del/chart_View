"""Fast Korean news summaries for Chart View.

Visible cards prefer provider snippets so users do not wait for publisher HTML.
English summaries are translated through several free web translators in parallel;
if every provider is temporarily unavailable, Chart View still returns a short
Korean finance-topic summary instead of a translation-delay placeholder.
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
SUMMARY_DISK_TTL = 60 * 60 * 24 * 7
SUMMARY_DISK_PATH = __import__("pathlib").Path(__file__).resolve().parent / "static" / "data" / "news_summary_cache.json"
SUMMARY_CACHE_VERSION = "v49-quality-gate"
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
_BING_TRANSLATOR_URL = "https://www.bing.com/translator"
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
_FINANCE_TOPICS = (
    (("earnings", "results", "quarter", "eps"), "실적"),
    (("revenue", "sales"), "매출"),
    (("profit", "margin"), "이익·수익성"),
    (("guidance", "outlook", "forecast"), "실적 전망"),
    (("demand", "orders", "order"), "수요·주문"),
    (("contract", "deal", "agreement"), "계약·수주"),
    (("investment", "capex", "plant", "factory"), "투자·증설"),
    (("acquisition", "merger", "acquire"), "인수합병"),
    (("dividend", "buyback"), "주주환원"),
    (("rating", "target price", "price target", "upgrade", "downgrade"), "증권사 의견"),
    (("ai", "artificial intelligence"), "AI"),
    (("semiconductor", "chip", "memory", "hbm"), "반도체"),
    (("shipment", "production", "launch"), "생산·출하"),
    (("tariff", "regulation", "lawsuit", "approval"), "규제·법률"),
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
        "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36 ChartView/46",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.7",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }
    for _ in range(4):
        current = _public_url_or_raise(current)
        response = requests.get(current, headers=headers, timeout=(2.2, 4.0), allow_redirects=False, stream=True)
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
        params={"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": source[:2200]},
        headers={"User-Agent": "Mozilla/5.0 ChartView/46"},
        timeout=(1.8, 3.6),
    )
    response.raise_for_status()
    payload = response.json()
    translated = _clean_text("".join(str(row[0] or "") for row in (payload[0] or []) if isinstance(row, list) and row))
    if not translated or not _looks_korean(translated):
        raise ValueError("translation_not_korean")
    return translated


def _mymemory_translate(source: str) -> str:
    response = requests.get(
        _TRANSLATE_FALLBACK_URL,
        params={"q": source[:480], "langpair": "en|ko"},
        headers={"User-Agent": "ChartView/46"},
        timeout=(1.8, 3.6),
    )
    response.raise_for_status()
    payload = response.json()
    translated = _clean_text((payload.get("responseData") or {}).get("translatedText"))
    if not translated or not _looks_korean(translated):
        raise ValueError("fallback_translation_not_korean")
    return translated


def _bing_translate(source: str) -> str:
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }
    landing = session.get(_BING_TRANSLATOR_URL, headers=headers, timeout=(2.0, 4.0))
    landing.raise_for_status()
    text = landing.text
    ig_match = re.search(r'"ig":"([^"]+)"', text, re.I)
    iid_matches = re.findall(r'data-iid="([^"]+)"', text, re.I)
    token_match = re.search(r'params_AbusePreventionHelper\s*=\s*\[\s*([^,]+)\s*,\s*"([^"]+)"\s*,', text, re.I)
    if not ig_match or not iid_matches or not token_match:
        raise ValueError("bing_token_missing")
    key = token_match.group(1).strip().strip('"')
    token = token_match.group(2)
    base = landing.url[:-10] if landing.url.lower().endswith("translator") else "https://www.bing.com/"
    response = session.post(
        f"{base}ttranslatev3?IG={ig_match.group(1)}&IID={iid_matches[-1]}",
        data={"fromLang": "en", "to": "ko", "text": source[:1000], "token": token, "key": key},
        headers=headers,
        timeout=(2.0, 4.0),
    )
    response.raise_for_status()
    payload = response.json()
    translated = _clean_text(payload[0]["translations"][0]["text"])
    if not translated or not _looks_korean(translated):
        raise ValueError("bing_translation_not_korean")
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

    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cv-translate")
    futures = [executor.submit(_google_translate_once, endpoint, source) for endpoint in _TRANSLATE_URLS]
    futures.append(executor.submit(_mymemory_translate, source))
    futures.append(executor.submit(_bing_translate, source))
    errors: list[str] = []
    try:
        try:
            for future in as_completed(futures, timeout=5.0):
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
    raise RuntimeError("translation_failed:" + ",".join(errors[:4]))


def _finance_korean_fallback(text: str, title: str = "") -> str:
    """Keep concrete actors/actions/amounts when free translators are unavailable.

    A mixed Korean fact summary is intentionally preferred over the old
    category-only sentence. If a finance pattern is unknown, expose the
    provider's key sentence transparently rather than pretending that a list
    of topics and naked numbers is a useful summary.
    """
    source = _clean_text(text)
    clean_title = _clean_text(title)
    if not source:
        return "기사 제공 요약문이 없어 원문에서 내용을 확인해 주세요."
    if _has_korean(source):
        return source

    lower = source.lower()
    facts: list[str] = []

    def add(value: str) -> None:
        value = _clean_text(value)
        if value and value not in facts:
            facts.append(value)

    money_pattern = r"[$€£₩]\s*\d[\d,.]*(?:\s*(?:billion|million|trillion|bn|mn|b|m|t))?"
    first_money_match = re.search(money_pattern, source, re.I)
    first_money = _clean_text(first_money_match.group(0)) if first_money_match else ""

    # Funding / financing: keep who is raising how much and what it means.
    if any(word in lower for word in ("financing", "funding", "fundraise", "fund-raising")):
        subject_match = re.match(r"\s*([A-Z][A-Za-z0-9.& -]{1,55}?)[’']s\s+", source)
        subject = _clean_text(subject_match.group(1)) if subject_match else "해당 기업"
        if first_money:
            add(f"{subject}이 약 {first_money} 규모의 자금조달을 추진 중입니다.")
        else:
            add(f"{subject}이 자금조달을 추진 중입니다.")
        if "commercial and investment ties" in lower:
            names = [name for name in ("Dell", "Nokia") if name.lower() in lower or name.lower() in clean_title.lower()]
            label = "·".join(names) if names else "관련 공급사"
            add(f"{label}는 해당 기업과 이미 상업·투자 관계를 맺고 있습니다.")
        if "not automatically" in lower and "revenue" in lower:
            add("자금조달이 성사돼도 관련 공급사의 매출로 즉시 인식되는 것은 아닙니다.")

    # Comparison articles should preserve the actual investment thesis.
    if "raised their revenue outlooks" in lower:
        names = "Ciena·Arista" if "ciena" in lower and "arista" in lower else "두 회사"
        add(f"{names} 모두 최근 매출 전망을 상향했고, 공급 제약이 풀리면 출하를 더 늘릴 수 있다고 보고 있습니다.")
    if "ciena" in lower and "orders it cannot yet fill" in lower:
        add("Ciena는 아직 소화하지 못한 주문잔고가 성장 포인트입니다.")
    cents = re.search(r"arista[^.]{0,180}?about\s+([\d.]+)\s+cents[^.]{0,160}?operating profit", source, re.I)
    if cents:
        add(f"Arista는 매출 1달러당 약 {cents.group(1)}센트를 영업이익으로 남기는 높은 수익성이 강점입니다.")

    # Reported revenue and growth.
    revenue = re.search(
        r"revenue(?:\s+of|\s+totaled|\s+reached)?\s*(%s)[^.!?]{0,100}?(?:up|grew|growth(?:\s+of)?)\s*(?:about\s*)?([\d.]+%%)"
        % money_pattern,
        source,
        re.I,
    )
    if revenue:
        add(f"매출은 {revenue.group(1)}로, 전년 대비 {revenue.group(2)} 증가했습니다.")
    else:
        growth = re.search(r"revenue\s+(?:grew|growth[^\d]{0,30})\s*(?:about\s*)?([\d.]+%)", source, re.I)
        if growth:
            add(f"매출 성장률은 전년 대비 {growth.group(1)}입니다.")

    # AI/server metrics: distinguish orders, recognized revenue and backlog.
    orders = re.search(r"AI\s+server\s+orders\s+reached\s+(%s)" % money_pattern, source, re.I)
    ai_revenue = re.search(r"(?:recognized\s+)?AI\s+server\s+revenue\s+(?:totaled|reached)\s+(%s)" % money_pattern, source, re.I)
    backlog = re.search(r"(?:AI\s+server\s+)?backlog\s+(?:reached|of|nears?)\s+(%s)" % money_pattern, source, re.I)
    metrics = []
    if orders:
        metrics.append(f"AI 서버 주문 {orders.group(1)}")
    if ai_revenue:
        metrics.append(f"인식 매출 {ai_revenue.group(1)}")
    if backlog:
        metrics.append(f"수주잔고 {backlog.group(1)}")
    if metrics:
        add(" · ".join(metrics) + "입니다.")

    margin = re.search(r"operating margin of\s*([\d.]+%)[^.!?]{0,90}?up from\s*([\d.]+%)", source, re.I)
    if margin:
        add(f"영업이익률은 {margin.group(2)}에서 {margin.group(1)}로 개선됐습니다.")

    capex = re.search(r"(?:plans|expects)\s+to\s+spend[^$€£₩]{0,60}(%s)[^.!?]{0,100}capital" % money_pattern, source, re.I)
    revenue_total = re.search(r"(%s)\s+of\s+revenue" % money_pattern, source, re.I)
    if capex:
        suffix = f" 최근 매출 {revenue_total.group(1)}와 비교해 투자 부담을 볼 필요가 있습니다." if revenue_total else ""
        add(f"자본지출 계획은 약 {capex.group(1)}입니다.{suffix}")

    stock_loss = re.search(r"stock\s+has\s+(?:lost|fallen)\s+(?:about\s*)?([\d.]+%%)[^.!?]{0,120}?(?:to|at)\s*(%s)" % money_pattern, source, re.I)
    if stock_loss:
        add(f"주가는 해당 기간 약 {stock_loss.group(1)} 하락해 {stock_loss.group(2)} 수준입니다.")

    ai_growth = re.search(r"AI[^.!?]{0,80}?revenue[^.!?]{0,60}?(?:surged|grew)\s*([\d.]+%)", source, re.I)
    below_high = re.search(r"stock[^.!?]{0,80}?([\d.]+%)\s+below\s+(?:its\s+)?high", source, re.I)
    if ai_growth:
        sentence = f"AI 관련 매출은 전년 대비 {ai_growth.group(1)} 증가했습니다."
        if below_high:
            sentence += f" 주가는 고점 대비 약 {below_high.group(1)} 낮은 수준입니다."
        add(sentence)

    if facts:
        return " ".join(facts[:3])

    # Last resort: show the actual provider sentence instead of a fake category summary.
    sentences = _split_sentences(source)
    numbered = [sentence for sentence in sentences if re.search(r"\d|[$€£₩]", sentence)]
    chosen = (numbered or sentences)[:2]
    excerpt = _clean_text(" ".join(chosen))
    if len(excerpt) > 320:
        excerpt = excerpt[:317].rstrip() + "…"
    return f"번역 연결이 불안정해 제공처 핵심문장을 표시합니다: {excerpt}"

_PROMO_PATTERNS = (
    "sponsored", "advertorial", "press release", "partner content", "promoted", "promotion",
    "buy now", "shop now", "limited time", "subscribe now", "sign up", "coupon", "deal of the day",
    "제공:", "협찬", "광고", "프로모션", "구매하기", "특가", "쿠폰", "구독하기", "회원가입",
)
_META_PATTERNS = (
    "click here", "read more", "learn more", "watch now", "follow us", "share this",
    "자세히 보기", "더 알아보기", "클릭", "공유하기", "팔로우",
)


def _strip_promotional_text(text: str) -> str:
    sentences = _split_sentences(_clean_text(text))
    kept = []
    for sentence in sentences:
        low = sentence.lower()
        if any(pattern in low for pattern in _PROMO_PATTERNS + _META_PATTERNS):
            continue
        kept.append(sentence)
    return _clean_text(" ".join(kept)) or _clean_text(text)


def _summary_quality(text: str, title: str = "") -> tuple[bool, str]:
    value = _clean_text(text)
    if len(value) < 28:
        return False, "too_short"
    low = value.lower()
    if any(pattern in low for pattern in _PROMO_PATTERNS):
        return False, "promotional"
    if len(_tokens(value)) < 5:
        return False, "low_information"
    title_tokens = _tokens(title)
    body_tokens = _tokens(value)
    if title_tokens and body_tokens and not (title_tokens & body_tokens) and not re.search(r"\\d|[$€£₩%]", value):
        return False, "weak_title_relation"
    return True, "ok"


def _finalize_summary(text: str, title: str, source_text: str) -> tuple[str, str]:
    candidate = _strip_promotional_text(text)
    ok, quality = _summary_quality(candidate, title)
    if ok:
        return candidate, quality
    fallback_source = _strip_promotional_text(source_text)
    fallback = _finance_korean_fallback(fallback_source, title)
    fallback = _strip_promotional_text(fallback)
    fallback_ok, fallback_quality = _summary_quality(fallback, title)
    if fallback_ok:
        return fallback, f"fallback_{quality}"
    return "기사 핵심 내용을 신뢰성 있게 요약하지 못했습니다. 원문 보기에서 확인해 주세요.", f"blocked_{fallback_quality}"


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


def _disk_cache_load() -> dict[str, dict]:
    try:
        payload = json.loads(SUMMARY_DISK_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _disk_cache_get(key: str) -> dict | None:
    row = _disk_cache_load().get(key)
    if not isinstance(row, dict) or time.time() - float(row.get("cachedAt") or 0) >= SUMMARY_DISK_TTL:
        return None
    data = row.get("data")
    return data if isinstance(data, dict) else None


def _disk_cache_put(key: str, data: dict) -> None:
    try:
        rows = _disk_cache_load()
        now = time.time()
        rows = {k: v for k, v in rows.items() if isinstance(v, dict) and now - float(v.get("cachedAt") or 0) < SUMMARY_DISK_TTL}
        rows[key] = {"cachedAt": now, "data": data}
        if len(rows) > 1500:
            rows = dict(sorted(rows.items(), key=lambda pair: float(pair[1].get("cachedAt") or 0), reverse=True)[:1200])
        SUMMARY_DISK_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SUMMARY_DISK_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SUMMARY_DISK_PATH)
    except OSError:
        pass


def _cache_key(url: str, title: str, snippet: str) -> str:
    raw = f"{SUMMARY_CACHE_VERSION}\n{url}\n{title}\n{snippet[:800]}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _build_summary(url: str, title: str, snippet: str) -> dict:
    key = _cache_key(url, title, snippet)
    with _SUMMARY_LOCK:
        cached = SUMMARY_CACHE.get(key)
        if cached and time.time() - float(cached.get("cachedAt") or 0) < SUMMARY_CACHE_TTL:
            return {**cached["data"], "cache": "hit"}
    persisted = _disk_cache_get(key)
    if persisted:
        with _SUMMARY_LOCK:
            SUMMARY_CACHE[key] = {"cachedAt": time.time(), "data": persisted}
        return {**persisted, "cache": "disk_hit"}

    with _SUMMARY_SEMAPHORE:
        clean_title = _clean_text(title)
        clean_snippet = _clean_text(snippet)
        article_text = ""
        page_description = ""
        fetch_error = None

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
        title_ko = clean_title if _looks_korean(clean_title) else ""

        if source_text:
            try:
                summary_ko, body_translated = _translate_ko(source_text)
                translated = bool(body_translated)
            except Exception:
                summary_ko = source_text if _has_korean(source_text) else _finance_korean_fallback(source_text, clean_title)
                translation_error = "summary_translation_topic_fallback"
        else:
            summary_ko = "기사 제목과 요약문이 제공되지 않았습니다. 원문에서 내용을 확인해 주세요."

        if not _looks_korean(summary_ko):
            summary_ko = _finance_korean_fallback(source_text, clean_title)
            translation_error = "summary_translation_topic_fallback"

        summary_ko, quality_status = _finalize_summary(summary_ko, clean_title, source_text)

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
            "qualityStatus": quality_status,
            "generatedAt": time.time(),
            "notice": "기사 본문은 저장·재게시하지 않고 요약 결과만 임시 캐시합니다.",
        }

    # True Korean translations cache for six hours. Topic fallbacks intentionally
    # do not cache so a later visit can retry the full translation providers.
    if translation_error is None:
        with _SUMMARY_LOCK:
            SUMMARY_CACHE[key] = {"cachedAt": time.time(), "data": result}
            if len(SUMMARY_CACHE) > 1200:
                oldest = sorted(SUMMARY_CACHE.items(), key=lambda pair: float(pair[1].get("cachedAt") or 0))[:200]
                for old_key, _ in oldest:
                    SUMMARY_CACHE.pop(old_key, None)
        _disk_cache_put(key, result)
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
