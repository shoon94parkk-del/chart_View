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
VIEW_NODE_RE = re.compile(
    r"(?P<var>node\d+)\['text'\]\s*=\s*[\"'](?P<title>.*?)[\"']\s*;.*?"
    r"(?P=var)\['rcpNo'\]\s*=\s*[\"'](?P<rcp>\d+)[\"']\s*;.*?"
    r"(?P=var)\['dcmNo'\]\s*=\s*[\"'](?P<dcm>\d+)[\"']\s*;.*?"
    r"(?P=var)\['eleId'\]\s*=\s*[\"'](?P<ele>\d+)[\"']\s*;.*?"
    r"(?P=var)\['offset'\]\s*=\s*[\"'](?P<offset>\d+)[\"']\s*;.*?"
    r"(?P=var)\['length'\]\s*=\s*[\"'](?P<length>\d+)[\"']\s*;.*?"
    r"(?P=var)\['dtd'\]\s*=\s*[\"'](?P<dtd>[^\"']+)[\"']",
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
    if not match:
        return None
    raw = _clean(match.group(1))
    # DART often writes compound units such as "천원, %" or "백만원, %".
    # Revenue amounts should carry only the monetary unit; share already has %.
    amount_unit = re.split(r"[,/·]", raw, maxsplit=1)[0].strip()
    return amount_unit or None


def _promote_embedded_header(frame: pd.DataFrame) -> pd.DataFrame:
    """DART frequently renders table headers as the first tbody row."""
    if frame is None or frame.empty:
        return frame
    columns = [_clean(col) for col in frame.columns]
    generic = all(
        re.fullmatch(r"(?:col_)?\d+", col or "")
        for col in columns
    )
    if not generic:
        return frame
    first = [_clean(value) for value in frame.iloc[0].tolist()]
    compact = [re.sub(r"\s+", "", value) for value in first]
    signals = sum(
        1
        for value in compact
        if any(token in value for token in ("품목", "제품", "서비스", "사업부문", "매출액", "매출", "비중", "비율", "구분"))
    )
    if signals < 2:
        return frame
    used: dict[str, int] = {}
    headers = []
    for idx, value in enumerate(first):
        base = value or f"col_{idx}"
        count = used.get(base, 0)
        used[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count+1}")
    promoted = frame.iloc[1:].copy().reset_index(drop=True)
    promoted.columns = headers
    return promoted


def _label_column(columns: list[str]) -> tuple[str | None, str]:
    priorities = [
        ("product", ("품목", "제품", "서비스")),
        ("segment", ("사업부문", "사업 부문", "부문")),
        ("category", ("구분", "매출유형", "매출 유형")),
    ]
    for kind, words in priorities:
        for col in columns:
            lowered = re.sub(r"\s+", "", col.lower())
            if any(re.sub(r"\s+", "", word.lower()) in lowered for word in words):
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
        if any(word in compact for word in ("매출비중", "매출비율", "비중", "비율", "구성비")):
            return col
    return None


def _row_label(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"^[\-·•]+\s*", "", text)
    return text[:100]


def _extract_table(frame: pd.DataFrame, html: str, report_year: int | None = None) -> dict | None:
    if frame is None or frame.empty or len(frame) > 100:
        return None
    frame = _promote_embedded_header(_flatten_columns(frame))
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
        if re.fullmatch(r"(합계|총계|소계|계|매출액합계|매출합계|매출총계|총매출)", compact_label):
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

    # DART HTML can use rowspan for revenue/share cells. pandas.read_html
    # forward-fills those cells into the following row, which can make an
    # otherwise valid product mix exceed 100%. Only collapse an *adjacent*
    # exact amount+share duplicate when doing so restores the explicit-share
    # total to roughly 100%; otherwise keep failing closed.
    if explicit_share_count:
        raw_share_sum = sum(row["share"] for row in rows if row["share"] is not None)
        if raw_share_sum > 105:
            collapsed_rows = []
            collapsed_count = 0
            for row in rows:
                previous = collapsed_rows[-1] if collapsed_rows else None
                duplicated_span = bool(
                    previous
                    and row["share"] is not None
                    and previous["share"] is not None
                    and row["name"] != previous["name"]
                    and abs(float(row["revenue"]) - float(previous["revenue"])) < 1e-9
                    and abs(float(row["share"]) - float(previous["share"])) < 1e-9
                )
                if duplicated_span:
                    collapsed_count += 1
                    continue
                collapsed_rows.append(row)
            collapsed_share_sum = sum(
                row["share"] for row in collapsed_rows if row["share"] is not None
            )
            if collapsed_count and 95 <= collapsed_share_sum <= 105:
                rows = collapsed_rows
                explicit_share_count = sum(row["share"] is not None for row in rows)
            else:
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

    # When DART exposes both detail rows and subtotal rows in the same table,
    # naïvely summing explicit shares can double-count a product. Reject such
    # candidates instead of normalising a clearly inconsistent disclosure.
    if explicit_share_count:
        explicit_share_sum = sum(
            item["share"] for item in items if item["_share_count"]
        )
        if explicit_share_sum > 105:
            return None

    revenue_sum = sum(item["revenue"] for item in items)
    if total_amount and revenue_sum > total_amount * 1.05:
        return None

    for item in items:
        if not item["_share_count"]:
            item["share"] = item["revenue"] / inferred_total * 100
        item["share"] = round(float(item["share"]), 2)
        item["revenue"] = round(float(item["revenue"]), 2)
        item.pop("_share_count", None)

    items = [item for item in items if 0.1 <= item["share"] <= 100.0]
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
    # Prefer actual product/segment disclosures over generic revenue-category
    # tables whenever both are present in the same business report.
    structured = [row for row in candidates if row.get("kind") in {"product", "segment"}]
    if structured:
        candidates = structured
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


def _viewer_nodes(page_html: str) -> list[dict]:
    nodes = []
    seen = set()
    for match in VIEW_NODE_RE.finditer(page_html or ""):
        node = {
            "title": _clean(html_lib.unescape(match.group("title"))),
            "rcp": match.group("rcp"),
            "dcm": match.group("dcm"),
            "ele": match.group("ele"),
            "offset": match.group("offset"),
            "length": match.group("length"),
            "dtd": match.group("dtd"),
        }
        key = (node["dcm"], node["ele"], node["offset"], node["length"])
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node)
    return nodes


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

    all_nodes = _viewer_nodes(main.text)
    nodes = [
        node for node in all_nodes
        if any(word in node["title"] for word in TARGET_SECTION_WORDS)
    ]
    # Prefer narrow sales/product sections over a broad business-content parent.
    nodes.sort(
        key=lambda x: (
            0 if any(word in x["title"] for word in TARGET_SECTION_WORDS[:5]) else 1,
            len(x["title"]),
        )
    )

    documents = []
    seen = set()
    for node in nodes[:8]:
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
