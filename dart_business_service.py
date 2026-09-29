"""DART business-report revenue mix for Korean listed companies.

The service is deliberately fail-closed:
- Prefer the official OpenDART API when DART_API_KEY is configured.
- Fall back to the public DART disclosure viewer at low frequency when no key exists.
- Only publish a revenue mix when a table has an explicit sales/revenue column.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import html as html_lib
import os
import re
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query
import pandas as pd
import requests

router = APIRouter()
KST = timezone(timedelta(hours=9))
DART_BASE = "https://dart.fss.or.kr"
OPEN_DART_BASE = "https://opendart.fss.or.kr/api"
CACHE_TTL = 7 * 24 * 3600
REQUEST_TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChartView/1.0; +https://chart-view-pkv8.onrender.com)",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CORP_CODES: tuple[float, dict[str, dict]] = (0.0, {})

REPORT_TITLE_RE = re.compile(r"(?:^|\])\s*사업보고서(?:\s*\(|\s*$)")
VIEW_DOC_RE = re.compile(
    r"text\s*:\s*[\"'](?P<title>.*?)[\"'].*?"
    r"viewDoc\(\s*[\"'](?P<rcp>\d+)[\"']\s*,\s*[\"'](?P<dcm>\d+)[\"']\s*,"
    r"\s*[\"'](?P<ele>\d+)[\"']\s*,\s*[\"'](?P<offset>\d+)[\"']\s*,"
    r"\s*[\"'](?P<length>\d+)[\"']\s*,\s*[\"'](?P<dtd>[^\"']+)[\"']",
    re.S,
)
TARGET_SECTION_WORDS = ("주요 제품", "주요제품", "매출 및 수주", "매출실적", "매출 실적", "사업의 내용")


def _clean(value) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _stock_code(ticker: str) -> str:
    raw = str(ticker or "").upper().strip()
    m = re.match(r"^(\d{6})(?:\.(?:KS|KQ))?$", raw)
    if not m:
        raise ValueError("Korean six-digit stock code required")
    return m.group(1)


def _number(value):
    if value is None:
        return None
    text = _clean(value).replace(",", "").replace(" ", "")
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("%", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", ".", "-."}:
        return None
    try:
        number = float(text)
        return -number if negative and number > 0 else number
    except ValueError:
        return None


def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
    copy = frame.copy()
    if isinstance(copy.columns, pd.MultiIndex):
        cols = []
        for parts in copy.columns:
            cleaned = []
            for part in parts:
                text = _clean(part)
                if text and not text.lower().startswith("unnamed"):
                    cleaned.append(text)
            cols.append(" / ".join(dict.fromkeys(cleaned)) or "구분")
        copy.columns = cols
    else:
        copy.columns = [
            _clean(col) if _clean(col) and not _clean(col).lower().startswith("unnamed") else f"col_{idx}"
            for idx, col in enumerate(copy.columns)
        ]
    return copy


def _detect_unit(html: str) -> str | None:
    text = BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)
    match = re.search(r"\(?\s*단위\s*[:：]\s*([^\)\n]{1,30})\)?", text)
    return _clean(match.group(1)) if match else None


def _label_column(columns: list[str]) -> tuple[str | None, str]:
    priorities = [
        ("product", ("품목", "제품", "서비스")),
        ("segment", ("사업부문", "사업 부문", "부문")),
        ("category", ("구분", "매출유형", "매출 유형")),
    ]
    for kind, words in priorities:
        for col in columns:
            lowered = col.lower()
            if any(word in lowered for word in words):
                return col, kind
    return (columns[0], "category") if columns else (None, "category")


def _amount_column(columns: list[str]) -> str | None:
    candidates = []
    for idx, col in enumerate(columns):
        compact = col.replace(" ", "")
        if "매출" not in compact:
            continue
        if any(bad in compact for bad in ("비중", "비율", "증감", "원가")):
            continue
        score = 3
        if "매출액" in compact:
            score += 3
        if any(token in compact for token in ("당기", "현재", "제", "기")):
            score += 1
        candidates.append((score, -idx, col))
    return max(candidates)[2] if candidates else None


def _share_column(columns: list[str]) -> str | None:
    for col in columns:
        compact = col.replace(" ", "")
        if any(word in compact for word in ("매출비중", "매출비율", "비중", "구성비")):
            return col
    return None


def _row_label(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"^[\-·•]+\s*", "", text)
    return text[:100]


def _extract_table(frame: pd.DataFrame, html: str, report_year: int | None = None) -> dict | None:
    if frame is None or frame.empty or len(frame) > 100:
        return None
    frame = _flatten_columns(frame)
    columns = list(frame.columns)
    label_col, kind = _label_column(columns)
    amount_col = _amount_column(columns)
    share_col = _share_column(columns)
    if not label_col or not amount_col:
        return None

    rows = []
    total_amount = None
    explicit_share_count = 0
    for _, raw in frame.iterrows():
        label = _row_label(raw.get(label_col))
        amount = _number(raw.get(amount_col))
        share = _number(raw.get(share_col)) if share_col else None
        if not label or amount is None or amount < 0:
            continue
        compact_label = re.sub(r"\s+", "", label)
        if re.fullmatch(r"(합계|총계|소계|계|매출액합계)", compact_label):
            total_amount = max(total_amount or 0, amount)
            continue
        if label in {"내수", "수출", "국내", "해외"}:
            continue
        if share is not None and 0 <= share <= 100:
            explicit_share_count += 1
        else:
            share = None
        rows.append({"name": label, "revenue": amount, "share": share})

    if len(rows) < 2:
        return None

    # Aggregate duplicate product/segment rows (e.g. domestic/export split).
    grouped: dict[str, dict] = {}
    for row in rows:
        key = row["name"]
        bucket = grouped.setdefault(key, {"name": key, "revenue": 0.0, "share": 0.0, "_share_count": 0})
        bucket["revenue"] += row["revenue"]
        if row["share"] is not None:
            bucket["share"] += row["share"]
            bucket["_share_count"] += 1

    items = list(grouped.values())
    inferred_total = total_amount or sum(item["revenue"] for item in items)
    if inferred_total <= 0:
        return None
    for item in items:
        if not item["_share_count"]:
            item["share"] = item["revenue"] / inferred_total * 100
        item["share"] = round(float(item["share"]), 2)
        item["revenue"] = round(float(item["revenue"]), 2)
        item.pop("_share_count", None)

    items = [item for item in items if item["share"] >= 0.1]
    items.sort(key=lambda x: (x["revenue"], x["share"]), reverse=True)
    if len(items) < 2:
        return None

    score = 10 + min(len(items), 8)
    if kind == "product":
        score += 8
    elif kind == "segment":
        score += 5
    if explicit_share_count:
        score += 4
    if report_year and any(str(report_year) in col for col in columns):
        score += 2

    return {
        "score": score,
        "kind": kind,
        "amountColumn": amount_col,
        "labelColumn": label_col,
        "unit": _detect_unit(html),
        "items": items[:8],
    }


def extract_revenue_mix(html_documents: list[str], report_year: int | None = None) -> dict | None:
    candidates = []
    for html in html_documents:
        if not html or "매출" not in html:
            continue
        try:
            tables = pd.read_html(StringIO(html))
        except Exception:
            continue
        for table in tables:
            parsed = _extract_table(table, html, report_year)
            if parsed:
                candidates.append(parsed)
    if not candidates:
        return None
    best = max(candidates, key=lambda x: x["score"])
    top = best["items"][0]
    return {
        "basis": "제품별 매출" if best["kind"] == "product" else "사업부문별 매출" if best["kind"] == "segment" else "매출 구분",
        "unit": best["unit"],
        "topItem": top,
        "items": best["items"][:5],
        "confidence": "high" if best["score"] >= 24 else "medium",
    }


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _search_report_web(company_name: str, stock_code: str) -> dict | None:
    session = _session()
    end = datetime.now(KST).date()
    start = end - timedelta(days=1100)
    try:
        session.get(f"{DART_BASE}/dsab001/main.do", timeout=REQUEST_TIMEOUT)
        response = session.post(
            f"{DART_BASE}/dsab001/search.ax",
            data={
                "textCrpNm": company_name or stock_code,
                "currentPage": 1,
                "maxResults": 100,
                "sort": "date",
                "series": "desc",
                "finalReport": "Y",
                "startDate": start.strftime("%Y%m%d"),
                "endDate": end.strftime("%Y%m%d"),
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None
    soup = BeautifulSoup(response.text, "lxml")
    for tr in soup.select("table tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        report_name = _clean(cells[2].get_text(" ", strip=True))
        if "사업보고서" not in report_name or "첨부" in report_name:
            continue
        link = cells[2].find("a", href=True)
        if not link:
            continue
        match = re.search(r"rcpNo=(\d{14})", link["href"])
        if not match:
            continue
        date_text = _clean(cells[4].get_text(" ", strip=True)) if len(cells) > 4 else ""
        return {
            "rceptNo": match.group(1),
            "reportName": report_name,
            "rceptDate": date_text,
            "sourceUrl": f"{DART_BASE}/dsaf001/main.do?rcpNo={match.group(1)}",
            "mode": "dart-web",
        }
    return None


def _corp_codes(api_key: str) -> dict[str, dict]:
    global _CORP_CODES
    with _CACHE_LOCK:
        if _CORP_CODES[1] and time.time() - _CORP_CODES[0] < 30 * 24 * 3600:
            return _CORP_CODES[1]
    response = requests.get(
        f"{OPEN_DART_BASE}/corpCode.xml",
        params={"crtfc_key": api_key},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    archive = zipfile.ZipFile(BytesIO(response.content))
    xml_bytes = archive.read(archive.namelist()[0])
    root = ET.fromstring(xml_bytes)
    mapping = {}
    for node in root.findall("list"):
        stock_code = _clean(node.findtext("stock_code"))
        if len(stock_code) != 6:
            continue
        mapping[stock_code] = {
            "corpCode": _clean(node.findtext("corp_code")),
            "corpName": _clean(node.findtext("corp_name")),
        }
    with _CACHE_LOCK:
        _CORP_CODES = (time.time(), mapping)
    return mapping


def _search_report_api(api_key: str, stock_code: str) -> dict | None:
    company = _corp_codes(api_key).get(stock_code)
    if not company:
        return None
    end = datetime.now(KST).date()
    start = end - timedelta(days=1100)
    response = requests.get(
        f"{OPEN_DART_BASE}/list.json",
        params={
            "crtfc_key": api_key,
            "corp_code": company["corpCode"],
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "last_reprt_at": "Y",
            "pblntf_ty": "A",
            "page_count": 100,
        },
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"000", None}:
        return None
    for item in payload.get("list") or []:
        report_name = _clean(item.get("report_nm"))
        if "사업보고서" not in report_name:
            continue
        rcept_no = _clean(item.get("rcept_no"))
        if not re.fullmatch(r"\d{14}", rcept_no):
            continue
        return {
            "rceptNo": rcept_no,
            "reportName": report_name,
            "rceptDate": _clean(item.get("rcept_dt")),
            "sourceUrl": f"{DART_BASE}/dsaf001/main.do?rcpNo={rcept_no}",
            "mode": "opendart-api",
        }
    return None


def _document_html_api(api_key: str, rcept_no: str) -> list[str]:
    response = requests.get(
        f"{OPEN_DART_BASE}/document.xml",
        params={"crtfc_key": api_key, "rcept_no": rcept_no},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    archive = zipfile.ZipFile(BytesIO(response.content))
    documents = []
    for name in archive.namelist():
        if len(documents) >= 8:
            break
        raw = archive.read(name)
        if len(raw) > 8_000_000:
            continue
        text = raw.decode("utf-8", "ignore")
        if "매출" in text:
            documents.append(text)
    return documents


def _viewer_sections_web(rcept_no: str) -> list[str]:
    session = _session()
    try:
        main = session.get(
            f"{DART_BASE}/dsaf001/main.do",
            params={"rcpNo": rcept_no},
            timeout=REQUEST_TIMEOUT,
        )
        main.raise_for_status()
    except requests.RequestException:
        return []

    nodes = []
    for match in VIEW_DOC_RE.finditer(main.text):
        title = _clean(html_lib.unescape(match.group("title")))
        if any(word in title for word in TARGET_SECTION_WORDS):
            nodes.append({key: match.group(key) for key in ("rcp", "dcm", "ele", "offset", "length", "dtd")} | {"title": title})
    # Prefer narrow sales/product sections over the full business section.
    nodes.sort(key=lambda x: (0 if any(word in x["title"] for word in TARGET_SECTION_WORDS[:5]) else 1, len(x["title"])))
    documents = []
    seen = set()
    for node in nodes[:5]:
        key = (node["dcm"], node["ele"], node["offset"], node["length"])
        if key in seen:
            continue
        seen.add(key)
        try:
            response = session.get(
                f"{DART_BASE}/report/viewer.do",
                params={
                    "rcpNo": node["rcp"],
                    "dcmNo": node["dcm"],
                    "eleId": node["ele"],
                    "offset": node["offset"],
                    "length": node["length"],
                    "dtd": node["dtd"],
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            if "매출" in response.text:
                documents.append(response.text)
        except requests.RequestException:
            continue
    return documents


def _report_year(report: dict) -> int | None:
    name = report.get("reportName") or ""
    match = re.search(r"\((\d{4})\.", name)
    if match:
        return int(match.group(1))
    date = re.sub(r"[^0-9]", "", str(report.get("rceptDate") or ""))
    if len(date) >= 4:
        return int(date[:4]) - 1
    return None


def fetch_business_report(ticker: str, company_name: str = "") -> dict:
    code = _stock_code(ticker)
    cache_key = code
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1]

    api_key = _clean(os.environ.get("DART_API_KEY"))
    report = None
    documents: list[str] = []
    mode = "dart-web"
    try:
        if api_key:
            report = _search_report_api(api_key, code)
            if report:
                documents = _document_html_api(api_key, report["rceptNo"])
                mode = "opendart-api"
    except Exception as exc:
        print(f"[DART] official API failed for {code}: {type(exc).__name__}: {exc}")

    if not report:
        report = _search_report_web(company_name, code)
        if report:
            documents = _viewer_sections_web(report["rceptNo"])
            mode = "dart-web"

    if not report:
        result = {
            "ticker": ticker,
            "stockCode": code,
            "available": False,
            "reason": "latest_business_report_not_found",
            "source": "DART",
            "checkedAt": datetime.now(KST).isoformat(timespec="seconds"),
        }
    else:
        year = _report_year(report)
        mix = extract_revenue_mix(documents, year)
        result = {
            "ticker": ticker,
            "stockCode": code,
            "available": bool(mix),
            "reportFound": True,
            "reportName": report.get("reportName"),
            "reportYear": year,
            "rceptDate": report.get("rceptDate"),
            "rceptNo": report.get("rceptNo"),
            "sourceUrl": report.get("sourceUrl"),
            "source": "OpenDART" if mode == "opendart-api" else "DART 공시뷰어",
            "sourceMode": mode,
            "basis": mix.get("basis") if mix else None,
            "unit": mix.get("unit") if mix else None,
            "topItem": mix.get("topItem") if mix else None,
            "items": mix.get("items") if mix else [],
            "confidence": mix.get("confidence") if mix else None,
            "reason": None if mix else "revenue_breakdown_table_not_confident",
            "checkedAt": datetime.now(KST).isoformat(timespec="seconds"),
        }

    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.time(), result)
    return result


@router.get("/api/business-report")
async def business_report(
    ticker: str = Query(..., min_length=6, max_length=12),
    name: str = Query("", max_length=80),
):
    try:
        code = _stock_code(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Keep this endpoint Korean-only. Overseas names must never be guessed from DART.
    if not code:
        raise HTTPException(status_code=400, detail="Korean ticker required")
    import asyncio
    return await asyncio.to_thread(fetch_business_report, ticker, name)
