"""DART business-report revenue mix for Korean listed companies.

The service is deliberately fail-closed:
- Prefer the official OpenDART API when DART_API_KEY is configured.
- Fall back to the public DART disclosure viewer at low frequency when no key exists.
- Only publish a revenue mix when a table has an explicit sales/revenue column.
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import html as html_lib
import json
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
import redis

router = APIRouter()
KST = timezone(timedelta(hours=9))
DART_BASE = "https://dart.fss.or.kr"
OPEN_DART_BASE = "https://opendart.fss.or.kr/api"
REPORT_CHECK_TTL = 24 * 3600
NEGATIVE_CACHE_TTL = 3600
REQUEST_TIMEOUT = 15
CORP_CODE_CACHE_PATH = os.path.join("static", "data", "dart_corp_codes.json")
BUSINESS_CONTEXT_CACHE_PATH = os.path.join("static", "data", "dart_business_context.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChartView/1.0; +https://chart-view-pkv8.onrender.com)",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_CORP_CODES: tuple[float, dict[str, dict]] = (0.0, {})
_STATIC_BUSINESS_CONTEXT: tuple[float, dict] = (0.0, {})
_REFRESHING: set[str] = set()
_REFRESH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dart-report-check")
_REDIS_CLIENT = None

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


def _static_business_context(code: str) -> dict | None:
    global _STATIC_BUSINESS_CONTEXT
    if os.environ.get("DART_STATIC_CACHE_BYPASS") == "1":
        return None
    try:
        mtime = os.path.getmtime(BUSINESS_CONTEXT_CACHE_PATH)
    except OSError:
        return None
    with _CACHE_LOCK:
        if _STATIC_BUSINESS_CONTEXT[1] and _STATIC_BUSINESS_CONTEXT[0] == mtime:
            payload = _STATIC_BUSINESS_CONTEXT[1]
        else:
            try:
                import json
                with open(BUSINESS_CONTEXT_CACHE_PATH, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception:
                return None
            _STATIC_BUSINESS_CONTEXT = (mtime, payload)
    # A validated annual report does not expire because the daily generator
    # found no change. Receipt-number revalidation happens in the background.
    row = (payload.get("companies") or {}).get(code) if isinstance(payload, dict) else None
    if not isinstance(row, dict) or not row.get("available"):
        return None
    return dict(row)


def _redis_client():
    global _REDIS_CLIENT
    url = os.environ.get("CHARTVIEW_ANALYTICS_REDIS", "").strip()
    if not url:
        return None
    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = redis.from_url(url, decode_responses=True,
                                       socket_connect_timeout=0.3, socket_timeout=0.3)
    return _REDIS_CLIENT


def _redis_key(code: str) -> str:
    return f"chartview:dart-business:v1:{code}"


def _load_persistent(code: str) -> tuple[float, dict] | None:
    try:
        client = _redis_client()
        raw = client.get(_redis_key(code)) if client else None
        payload = json.loads(raw) if raw else None
        row = payload.get("row") if isinstance(payload, dict) else None
        if (isinstance(row, dict) and row.get("available") is True
                and row.get("stockCode") == code
                and re.fullmatch(r"\d{14}", str(row.get("rceptNo") or ""))):
            return float(payload.get("verifiedAt") or 0), row
    except Exception as exc:
        print(f"[DART] persistent cache read failed for {code}: {type(exc).__name__}")
    return None


def _save_persistent(code: str, row: dict, verified_at: float) -> None:
    if not row.get("available") or not row.get("rceptNo"):
        return
    try:
        client = _redis_client()
        if client:
            client.set(_redis_key(code), json.dumps({"verifiedAt": verified_at, "row": row}, ensure_ascii=False))
    except Exception as exc:
        print(f"[DART] persistent cache write failed for {code}: {type(exc).__name__}")


def _refresh_cached_report(code: str, ticker: str, company_name: str, old: dict) -> None:
    try:
        api_key = _clean(os.environ.get("DART_API_KEY"))
        report = _search_report_api(api_key, code) if api_key else None
        if not report:
            report = _search_report_web(company_name, code)
        if not report:
            # A provider error must not erase a validated report.
            with _CACHE_LOCK:
                _CACHE[code] = (time.time() - REPORT_CHECK_TTL + NEGATIVE_CACHE_TTL, old)
            return
        if report["rceptNo"] == old.get("rceptNo"):
            checked = time.time()
            with _CACHE_LOCK:
                _CACHE[code] = (checked, old)
            _save_persistent(code, old, checked)
            return
        newer = fetch_business_report(ticker, company_name, force=True, report_hint=report)
        if not newer.get("available"):
            with _CACHE_LOCK:
                _CACHE[code] = (time.time() - REPORT_CHECK_TTL + NEGATIVE_CACHE_TTL, old)
    except Exception as exc:
        print(f"[DART] report check failed for {code}: {type(exc).__name__}: {exc}")
        with _CACHE_LOCK:
            _CACHE[code] = (time.time() - REPORT_CHECK_TTL + NEGATIVE_CACHE_TTL, old)
    finally:
        with _CACHE_LOCK:
            _REFRESHING.discard(code)


def _schedule_report_check(code: str, ticker: str, company_name: str, row: dict) -> None:
    if os.environ.get("DART_STATIC_CACHE_BYPASS") == "1":
        return
    with _CACHE_LOCK:
        if code in _REFRESHING:
            return
        _REFRESHING.add(code)
    _REFRESH_POOL.submit(_refresh_cached_report, code, ticker, company_name, row)


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
    negative = (text.startswith("(") and text.endswith(")")) or text.startswith("△")
    text = text.lstrip("△").strip("()").replace("%", "")
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
    # A business-report section can contain many unrelated tables before the
    # revenue table (e.g. emissions in tCO2e). Never label revenue with a
    # non-monetary unit just because it appears first in the HTML.
    for match in re.finditer(r"\(?\s*단위\s*[:：]\s*([^\)\n]{1,30})\)?", text):
        raw = _clean(match.group(1))
        amount_unit = re.split(r"[,/·]", raw, maxsplit=1)[0].strip()
        compact = re.sub(r"\s+", "", amount_unit).lower()
        monetary = bool(
            re.search(r"(?:원|krw|usd|달러|dollar|천원|백만원|억원|조원)", compact, re.I)
        )
        if monetary:
            return amount_unit
    return None


def _promote_embedded_header(frame: pd.DataFrame) -> pd.DataFrame:
    """Promote one or two tbody rows when DART embeds multi-row headers."""
    if frame is None or frame.empty:
        return frame
    columns = [_clean(col) for col in frame.columns]
    generic = all(re.fullmatch(r"(?:col_)?\d+", col or "") for col in columns)
    if not generic:
        return frame

    max_depth = min(3, len(frame))
    chosen = None
    for depth in range(1, max_depth + 1):
        combined = []
        for col_idx in range(len(columns)):
            parts = []
            for row_idx in range(depth):
                text = _clean(frame.iloc[row_idx, col_idx])
                if text and text not in parts:
                    parts.append(text)
            combined.append(" / ".join(parts))
        compact = [re.sub(r"\s+", "", value) for value in combined]
        has_label = any(
            any(token in value for token in ("품목", "제품", "서비스", "사업부문", "부문", "구분", "주요제품"))
            for value in compact
        )
        has_value = any(
            any(token in value for token in ("매출액", "금액", "영업수익"))
            or bool(re.search(r"(?:^|/)매출(?:/|$)", value))
            for value in compact
        )
        has_share = any(any(token in value for token in ("비중", "비율", "구성비")) for value in compact)
        if has_label and has_value:
            chosen = (depth, combined)
            break
    if not chosen:
        return frame

    depth, combined = chosen
    used: dict[str, int] = {}
    headers = []
    for idx, value in enumerate(combined):
        base = value or f"col_{idx}"
        count = used.get(base, 0)
        used[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count+1}")
    promoted = frame.iloc[depth:].copy().reset_index(drop=True)
    promoted.columns = headers
    return promoted


def _label_column(columns: list[str]) -> tuple[str | None, str]:
    compact = [(col, re.sub(r"\s+", "", col.lower())) for col in columns]
    segment_cols = [col for col, lowered in compact if "부문" in lowered]
    product_cols = [col for col, lowered in compact if any(word in lowered for word in ("품목", "제품", "서비스"))]
    # When a table explicitly gives both a business division and its major
    # product list (Samsung is a representative case), the revenue belongs to
    # the division. Show the division as the revenue item and keep products as
    # descriptive detail instead of pretending each listed product has the
    # division's full revenue.
    if segment_cols and product_cols:
        return segment_cols[0], "segment"
    priorities = [
        ("product", ("품목", "제품", "서비스")),
        ("segment", ("사업부문", "사업 부문", "부문")),
        ("category", ("구분", "매출유형", "매출 유형")),
    ]
    for kind, words in priorities:
        for col, lowered in compact:
            if any(re.sub(r"\s+", "", word.lower()) in lowered for word in words):
                return col, kind
    return (columns[0], "category") if columns else (None, "category")


def _repeated_revenue_metric_pair(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    groups: dict[str, list[str]] = {}
    for col in frame.columns:
        compact = re.sub(r"\s+", "", str(col))
        if "매출" not in compact or any(token in compact for token in ("원가", "채권", "이익")):
            continue
        base = re.sub(r"_\d+$", "", compact)
        groups.setdefault(base, []).append(col)
    for cols in groups.values():
        if len(cols) < 2:
            continue
        amount_col = None
        share_col = None
        for col in cols:
            samples = [_clean(value) for value in frame[col].head(30).tolist()]
            meaningful = [value for value in samples if value and value not in {"-", "—"}]
            if not meaningful:
                continue
            percent_ratio = sum("%" in value for value in meaningful) / len(meaningful)
            if percent_ratio >= 0.5:
                share_col = share_col or col
            else:
                numeric_ratio = sum(_number(value) is not None for value in meaningful) / len(meaningful)
                if numeric_ratio >= 0.5:
                    amount_col = amount_col or col
        if amount_col and share_col:
            return amount_col, share_col
    return None, None


def _combined_amount_share_column(columns: list[str]) -> str | None:
    for col in columns:
        compact = re.sub(r"\s+", "", col)
        if re.search(r"(?:매출액|매출금액|금액)\((?:비중|비율|%)\)", compact):
            return col
    return None


def _amount_share(value) -> tuple[float | None, float | None]:
    text = _clean(value)
    if not text:
        return None, None
    share_match = re.search(r"\(?\s*([△\-]?[0-9][0-9,.]*)\s*%\s*\)?", text)
    share = _number(share_match.group(1)) if share_match else None
    amount_text = re.sub(r"\([^)]*%[^)]*\)", "", text)
    if share_match and share_match.group(0) == text:
        amount = None
    else:
        amount = _number(amount_text)
    return amount, share


def _amount_column(columns: list[str], allow_generic: bool = False) -> str | None:
    candidates = []
    for idx, col in enumerate(columns):
        compact = re.sub(r"\s+", "", col)
        explicit_amount = any(token in compact for token in ("매출액", "매출금액", "영업수익"))
        if not explicit_amount and compact not in {"매출", "수익"}:
            continue
        if any(bad in compact for bad in ("비중", "비율", "증감", "원가", "유형", "채권", "이익")):
            continue
        score = 3
        if "매출액" in compact or "영업수익" in compact:
            score += 3
        if any(token in compact for token in ("당기", "현재", "제", "기")):
            score += 1
        candidates.append((score, -idx, col))
    if candidates:
        return max(candidates)[2]
    if allow_generic:
        for col in columns:
            compact = re.sub(r"\s+", "", col)
            if "금액" in compact and not any(token in compact for token in ("비중", "비율", "증감")):
                return col
    return None


def _share_column(columns: list[str]) -> str | None:
    for col in columns:
        compact = col.replace(" ", "")
        if any(word in compact for word in ("매출비중", "매출비율", "비중", "비율", "구성비")):
            return col
    return None


def _row_label(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"^[\-·•]+\s*", "", text)
    # DART's cell layout can insert spaces between the syllables of a short
    # segment name; keep the actual words readable without rewriting labels.
    text = re.sub(r"(?<!\S)사\s+업\s+부\s+문(?=\s|$)", "사업부문", text)
    text = re.sub(r"(?<!\S)가\s+스(?=\s|$)", "가스", text)
    return text[:100]


def _latest_period_amount_column(columns: list[str]) -> str | None:
    for col in columns:
        compact = re.sub(r"\s+", "", col)
        if any(token in compact for token in ("비중", "비율", "구성비")):
            continue
        if re.search(r"(제\d+기|20\d{2}년|당기)", compact):
            return col
    return None


def _sum_dimension_column(frame: pd.DataFrame, label_col: str | None) -> str | None:
    for col in frame.columns:
        if col == label_col:
            continue
        values = {re.sub(r"\s+", "", _clean(value)) for value in frame[col].head(40).tolist()}
        if "합계" in values and ({"내수", "수출"} & values):
            return col
    return None


def _metric_column(frame: pd.DataFrame, label_col: str | None) -> str | None:
    for col in frame.columns:
        if col == label_col:
            continue
        values = {
            re.sub(r"\s+", "", _clean(value))
            for value in frame[col].head(30).tolist()
        }
        if any(value in {"매출액", "영업수익", "매출", "수익"} for value in values):
            return col
    return None


def _is_total_label(label: str, share: float | None = None) -> bool:
    compact = re.sub(r"\s+", "", label)
    if re.fullmatch(r"(합계|총계|소계|계|매출액합계|매출합계|매출총계|총매출|영업수익합계|연결조정후|연결조정후합계)", compact):
        return True
    if compact in {"영업수익", "매출액", "매출"} and share is not None and 95 <= share <= 105:
        return True
    return False


def _extract_period_segment_sales(frame: pd.DataFrame, html: str) -> dict | None:
    """Read a sales table whose current-period amounts are split by segment.

    Shipbuilders often disclose domestic/export rows under a business segment
    and put the revenue amount under ``제N기`` instead of ``매출액``. Require an
    explicit total and reconcile it with any named consolidation adjustment.
    """
    frame = _promote_embedded_header(_flatten_columns(frame))
    columns = list(frame.columns)
    segment_col = next((c for c in columns if "사업부문" in re.sub(r"\s+", "", c)), None)
    type_col = next((c for c in columns if "매출유형" in re.sub(r"\s+", "", c)), None)
    period_col = _latest_period_amount_column(columns)
    if not segment_col or not type_col or not period_col or len(frame) > 80:
        return None
    groups: dict[str, float] = {}
    total = None
    adjustment = 0.0
    for _, raw in frame.iterrows():
        label = _row_label(raw.get(segment_col))
        amount = _number(raw.get(period_col))
        if not label or amount is None:
            continue
        compact = re.sub(r"\s+", "", label)
        if _is_total_label(label):
            total = amount
        elif "연결조정" in compact or (amount < 0 and "조정" in compact):
            adjustment += amount
        elif amount > 0 and re.search(r"제품|상품|용역|서비스|기타", _clean(raw.get(type_col))):
            groups[label] = groups.get(label, 0.0) + amount
    if total is None or total <= 0 or len(groups) < 2:
        return None
    if abs(sum(groups.values()) + adjustment - total) > total * 0.01:
        return None
    items = [{"name": name, "revenue": round(amount, 2), "share": round(amount / total * 100, 2)}
             for name, amount in groups.items()]
    if any(item["share"] > 100 for item in items):
        return None
    items.sort(key=lambda item: item["revenue"], reverse=True)
    return {
        "score": 28,
        "kind": "segment",
        "amountColumn": period_col,
        "labelColumn": segment_col,
        "unit": _detect_unit(html),
        "items": items[:8],
        "hasExplicitShare": False,
        "shareSum": round((sum(groups.values()) + adjustment) / total * 100, 2),
        "complete": True,
        "totalAmount": round(total, 2),
        "coveredSegments": [],
        "hasConsolidationAdjustment": adjustment != 0,
        "positiveSegmentTotal": round(sum(groups.values()), 2),
        "adjustmentAmount": round(adjustment, 2),
    }


def _extract_table(frame: pd.DataFrame, html: str, report_year: int | None = None) -> dict | None:
    if frame is None or frame.empty or len(frame) > 120:
        return None
    frame = _promote_embedded_header(_flatten_columns(frame))
    columns = list(frame.columns)
    label_col, kind = _label_column(columns)
    share_col = _share_column(columns)
    repeated_amount_col, repeated_share_col = _repeated_revenue_metric_pair(frame)
    if not share_col and repeated_share_col:
        share_col = repeated_share_col
    combined_col = _combined_amount_share_column(columns)
    if combined_col:
        sample_values = [_clean(value) for value in frame[combined_col].head(20).tolist()]
        has_true_combined_cell = any(
            re.search(r"[0-9][0-9,.]*\s*\([^)]*[0-9][0-9,.]*\s*%\)", value)
            for value in sample_values
        )
        if not has_true_combined_cell:
            combined_col = None

    # When one business segment is repeated across multiple separately priced
    # products/services, the disclosed revenue belongs to the product rows.
    # In that case switch from the segment label to the product label. When
    # segment/product are one-to-one (Samsung Electronics), keep segment basis.
    segment_col = next((col for col in columns if "부문" in re.sub(r"\s+", "", col)), None)
    product_col = next(
        (col for col in columns if any(word in re.sub(r"\s+", "", col) for word in ("품목", "제품", "서비스", "주요제품"))),
        None,
    )
    if not segment_col:
        # Some DART tables call the segment column simply "구분". Infer it
        # from values such as "플랫폼 부문 / 콘텐츠 부문" rather than from
        # the header text alone.
        for col in columns:
            values = [
                _row_label(value)
                for value in frame[col].head(40).tolist()
                if _row_label(value)
            ]
            meaningful = [
                value for value in values
                if not _is_total_label(value)
                and value not in {"매출액", "영업이익", "영업손익", "총자산", "자산"}
            ]
            if not meaningful:
                continue
            segment_like = [value for value in meaningful if "부문" in re.sub(r"\s+", "", value)]
            if len(segment_like) >= 2 and len(segment_like) >= max(2, len(meaningful) // 2):
                segment_col = col
                label_col = col
                kind = "segment"
                break

    switched_product = False
    if kind == "segment" and segment_col and product_col:
        pairs = []
        for _, raw in frame.head(40).iterrows():
            seg = _row_label(raw.get(segment_col))
            prod = _row_label(raw.get(product_col))
            if not seg or not prod or _is_total_label(seg) or _is_total_label(prod):
                continue
            pairs.append((seg, prod))
        segment_names = {seg for seg, _ in pairs}
        product_names = {prod for _, prod in pairs}
        if pairs and len(product_names) > len(segment_names):
            label_col = product_col
            kind = "product"
            switched_product = True

    amount_col = combined_col or repeated_amount_col or _amount_column(columns, allow_generic=bool(share_col))
    sum_dimension_col = None
    if not amount_col and not share_col:
        sum_dimension_col = _sum_dimension_column(frame, label_col)
        if sum_dimension_col:
            amount_col = _latest_period_amount_column(columns)
    if not label_col or not amount_col:
        return None

    if switched_product and segment_col and product_col:
        # Some disclosures repeat one segment's exact revenue/share on every
        # sub-service row (e.g. Kakao platform sub-services). Those are not
        # product-level revenues. If multiple products under the same segment
        # carry the identical disclosed amount/share, revert to segment basis.
        by_segment: dict[str, list[tuple[str, float | None, float | None]]] = {}
        for _, raw in frame.head(50).iterrows():
            seg = _row_label(raw.get(segment_col))
            prod = _row_label(raw.get(product_col))
            if not seg or not prod or _is_total_label(seg) or _is_total_label(prod):
                continue
            if combined_col:
                amt, shr = _amount_share(raw.get(combined_col))
            else:
                amt = _number(raw.get(amount_col))
                shr = _number(raw.get(share_col)) if share_col else None
            if amt is None:
                continue
            by_segment.setdefault(seg, []).append((prod, amt, shr))
        repeated_segment_total = False
        for entries in by_segment.values():
            if len({prod for prod, _, _ in entries}) < 2:
                continue
            values = {(round(float(amt), 6), None if shr is None else round(float(shr), 6)) for _, amt, shr in entries}
            if len(values) == 1:
                repeated_segment_total = True
                break
        if repeated_segment_total:
            label_col = segment_col
            kind = "segment"
            switched_product = False

    generic_amount = combined_col is None and "매출" not in re.sub(r"\s+", "", amount_col)
    metric_col = _metric_column(frame, label_col) if generic_amount and not sum_dimension_col else None

    detail_col = None
    if switched_product:
        detail_col = segment_col
    elif kind == "segment":
        for col in columns:
            lowered = re.sub(r"\s+", "", col.lower())
            if any(word in lowered for word in ("품목", "제품", "서비스", "주요제품")):
                detail_col = col
                break

    rows = []
    total_amount = None
    explicit_share_count = 0
    adjustment_amount = 0.0
    adjustment_share = 0.0

    for _, raw in frame.iterrows():
        label = _row_label(raw.get(label_col))
        if not label:
            continue

        if metric_col:
            metric = re.sub(r"\s+", "", _clean(raw.get(metric_col)))
            metric = re.sub(r"^\d+[.)]?", "", metric)
            if metric not in {"매출액", "영업수익", "매출", "수익"}:
                continue

        if sum_dimension_col:
            dimension = re.sub(r"\s+", "", _clean(raw.get(sum_dimension_col)))
            if dimension not in {"합계", "계", "소계"}:
                continue

        if combined_col:
            amount, share = _amount_share(raw.get(combined_col))
        else:
            amount = _number(raw.get(amount_col))
            share = _number(raw.get(share_col)) if share_col else None

        if amount is None:
            continue

        if _is_total_label(label, share):
            if amount >= 0:
                total_amount = max(total_amount or 0, amount)
            continue

        raw_text = " ".join(_clean(value) for value in raw.tolist())
        if amount < 0:
            if re.search(r"내부거래|내부매출|제거|조정|상계", raw_text):
                adjustment_amount += amount
                if share is not None and share < 0:
                    adjustment_share += share
            continue

        if label in {"내수", "수출", "국내", "해외"}:
            continue
        if share is not None and 0 <= share <= 100:
            explicit_share_count += 1
        else:
            share = None

        row = {"name": label, "revenue": amount, "share": share}
        if detail_col:
            detail = _clean(raw.get(detail_col))
            if detail and detail != label:
                row["detail"] = detail[:180]
        rows.append(row)

    if not rows:
        return None
    if sum_dimension_col and total_amount is None:
        return None

    if kind == "segment":
        # Some tables repeat the exact segment total on each descriptive
        # sub-service/product row. Count that disclosed segment total once.
        deduped = []
        seen_segment_totals = set()
        for row in rows:
            key = (
                row["name"],
                round(float(row["revenue"]), 6),
                None if row["share"] is None else round(float(row["share"]), 6),
            )
            if key in seen_segment_totals:
                continue
            seen_segment_totals.add(key)
            deduped.append(row)
        rows = deduped
        explicit_share_count = sum(row["share"] is not None for row in rows)

    if kind == "category":
        segment_like = sum("부문" in row["name"] for row in rows)
        if segment_like and segment_like >= max(1, len(rows) // 2):
            kind = "segment"

    # DART rowspan forward-fill can duplicate the same amount/share into the
    # next label. Collapse only when removing exact adjacent duplicates restores
    # the disclosed share total to approximately 100%.
    if explicit_share_count:
        raw_share_sum = sum(row["share"] for row in rows if row["share"] is not None)
        effective_share_sum = raw_share_sum + adjustment_share
        if raw_share_sum > 105 and not (95 <= effective_share_sum <= 105):
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
            if collapsed_count and 95 <= collapsed_share_sum + adjustment_share <= 105:
                rows = collapsed_rows
                explicit_share_count = sum(row["share"] is not None for row in rows)
            else:
                return None

    grouped: dict[str, dict] = {}
    for row in rows:
        key = row["name"]
        bucket = grouped.setdefault(key, {"name": key, "revenue": 0.0, "share": 0.0, "_share_count": 0})
        if row.get("detail") and not bucket.get("detail"):
            bucket["detail"] = row["detail"]
        bucket["revenue"] += row["revenue"]
        if row["share"] is not None:
            bucket["share"] += row["share"]
            bucket["_share_count"] += 1

    items = list(grouped.values())
    if not items:
        return None

    inferred_total = total_amount or sum(item["revenue"] for item in items)
    if inferred_total <= 0:
        return None

    explicit_share_sum = 0.0
    if explicit_share_count:
        explicit_share_sum = sum(item["share"] for item in items if item["_share_count"])
        if explicit_share_sum > 105 and not (95 <= explicit_share_sum + adjustment_share <= 105):
            return None

    revenue_sum = sum(item["revenue"] for item in items)
    adjusted_revenue_sum = revenue_sum + adjustment_amount
    if total_amount and adjusted_revenue_sum > total_amount * 1.05:
        return None

    for item in items:
        if not item["_share_count"]:
            item["share"] = item["revenue"] / inferred_total * 100
        item["share"] = round(float(item["share"]), 2)
        item["revenue"] = round(float(item["revenue"]), 2)
        item.pop("_share_count", None)

    items = [item for item in items if 0.1 <= item["share"] <= 100.0]
    items.sort(key=lambda x: (x["share"], x["revenue"]), reverse=True)
    if not items:
        return None

    if kind == "category":
        geography_labels = {"국내외", "국내", "해외", "내수", "수출", "수출및내수", "내수및수출"}
        normalized_names = {re.sub(r"\s+", "", item["name"]) for item in items}
        if normalized_names and normalized_names <= geography_labels:
            return None
        if any(name in geography_labels for name in normalized_names) and len(normalized_names) <= 2:
            return None

    share_sum = round(sum(item["share"] for item in items) + adjustment_share, 2) if explicit_share_count else 100.0
    complete = (95 <= share_sum <= 105) if explicit_share_count else True
    if len(items) == 1 and not complete:
        # Keep partial one-segment candidates only for cross-table merging.
        pass

    score = 10 + min(len(items), 8)
    if kind == "product":
        score += 8
    elif kind == "segment":
        score += 5
    if explicit_share_count:
        score += 4
    if complete:
        score += 3
    if report_year and any(str(report_year) in col for col in columns):
        score += 2

    covered_segments = sorted({
        _clean(item.get("detail"))
        for item in items
        if _clean(item.get("detail")) and kind == "product"
    })
    return {
        "score": score,
        "kind": kind,
        "amountColumn": amount_col,
        "labelColumn": label_col,
        "unit": _detect_unit(html),
        "items": items[:8],
        "hasExplicitShare": bool(explicit_share_count),
        "shareSum": share_sum,
        "complete": complete,
        "totalAmount": round(float(total_amount or sum(item["revenue"] for item in items)), 2),
        "coveredSegments": covered_segments,
        "hasConsolidationAdjustment": bool(adjustment_amount or adjustment_share),
        "positiveSegmentTotal": round(revenue_sum, 2),
        "adjustmentAmount": round(adjustment_amount, 2),
    }


def _merge_segment_candidates(candidates: list[dict]) -> dict | None:
    partials = [
        row for row in candidates
        if row.get("kind") == "segment"
        and row.get("hasExplicitShare")
        and 0 < float(row.get("shareSum") or 0) < 95
    ]
    best = None
    for i, left in enumerate(partials):
        left_names = {item["name"] for item in left["items"]}
        for right in partials[i + 1:]:
            right_names = {item["name"] for item in right["items"]}
            if left_names & right_names:
                continue
            share_sum = float(left.get("shareSum") or 0) + float(right.get("shareSum") or 0)
            if not 95 <= share_sum <= 105:
                continue
            items = [*left["items"], *right["items"]]
            items.sort(key=lambda x: (x["share"], x["revenue"]), reverse=True)
            merged = {
                "score": max(left["score"], right["score"]) + 5,
                "kind": "segment",
                "unit": left.get("unit") or right.get("unit"),
                "items": items[:8],
                "hasExplicitShare": True,
                "shareSum": round(share_sum, 2),
                "complete": True,
            }
            if best is None or merged["score"] > best["score"]:
                best = merged
    return best


def extract_revenue_mix(html_documents: list[str], report_year: int | None = None) -> dict | None:
    candidates = []
    seen = set()
    for html in html_documents:
        if not html or ("매출" not in html and "영업수익" not in html):
            continue
        try:
            tables = pd.read_html(StringIO(html))
        except Exception:
            continue
        for table in tables:
            parsed = _extract_table(table, html, report_year) or _extract_period_segment_sales(table, html)
            if not parsed:
                continue
            signature = (
                parsed.get("kind"),
                tuple((item.get("name"), item.get("share")) for item in parsed.get("items") or []),
            )
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append(parsed)

    if not candidates:
        return None

    merged = _merge_segment_candidates(candidates)
    if merged:
        candidates.append(merged)

    complete_candidates = [row for row in candidates if row.get("complete")]
    if not complete_candidates:
        return None

    segment_candidates = [
        row for row in complete_candidates
        if row.get("kind") == "segment" and len(row.get("items") or []) >= 2
    ]
    reference_segment = max(segment_candidates, key=lambda row: row["score"]) if segment_candidates else None

    product_candidates = [row for row in complete_candidates if row.get("kind") == "product"]
    if reference_segment:
        reference_names = {
            re.sub(r"\s+", "", item.get("name", "")).replace("사업", "")
            for item in reference_segment.get("items") or []
        }
        scoped_products = []
        for row in product_candidates:
            covered = {
                re.sub(r"\s+", "", name).replace("사업", "")
                for name in row.get("coveredSegments") or []
            }
            if not covered:
                continue
            matched = 0
            for name in covered:
                if any(name in ref or ref in name for ref in reference_names if name and ref):
                    matched += 1
            if matched >= max(1, len(covered) // 2):
                scoped_products.append(row)
        product_candidates = scoped_products

    priority_groups = [
        [row for row in product_candidates if row.get("hasExplicitShare")],
        [row for row in complete_candidates if row.get("kind") == "segment" and row.get("hasExplicitShare")],
        product_candidates,
        [row for row in complete_candidates if row.get("kind") == "segment"],
    ]
    for group in priority_groups:
        if group:
            complete_candidates = group
            break

    best = max(complete_candidates, key=lambda x: x["score"])
    top = best["items"][0]
    return {
        "basis": "제품별 매출" if best["kind"] == "product" else "사업부문별 매출" if best["kind"] == "segment" else "매출 구분",
        "unit": best.get("unit"),
        "topItem": top,
        "items": best["items"][:5],
        "confidence": "high" if best["score"] >= 24 else "medium",
        "hasConsolidationAdjustment": bool(best.get("hasConsolidationAdjustment")),
        "revenueBasis": {
            "denominator": "공시 연결조정 후 매출액" if best.get("hasConsolidationAdjustment") else "공시 매출 합계",
            "totalAmount": best.get("totalAmount"),
            "positiveSegmentTotal": best.get("positiveSegmentTotal"),
            "adjustmentAmount": best.get("adjustmentAmount"),
            "reconciled": bool(best.get("totalAmount") and best.get("positiveSegmentTotal") is not None and best.get("adjustmentAmount") is not None and abs(best["positiveSegmentTotal"] + best["adjustmentAmount"] - best["totalAmount"]) <= best["totalAmount"] * .01),
        },
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

    # Runtime requests must not download the entire DART corp-code archive.
    # A GitHub workflow materialises the public stock_code -> corp_code mapping
    # into the repo so cold starts stay fast.
    try:
        if os.path.exists(CORP_CODE_CACHE_PATH):
            import json
            with open(CORP_CODE_CACHE_PATH, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            mapping = payload.get("companies") if isinstance(payload, dict) else payload
            if isinstance(mapping, dict) and mapping:
                with _CACHE_LOCK:
                    _CORP_CODES = (time.time(), mapping)
                return mapping
    except Exception as exc:
        print(f"[DART] local corp-code cache failed: {type(exc).__name__}: {exc}")

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
        if "첨부정정" in report_name:
            # An attachment correction can contain only audit statements. The
            # public DART search resolves the latest full business-report body.
            return None
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
    specific_nodes = [
        node for node in nodes
        if any(word in node["title"] for word in TARGET_SECTION_WORDS[:5])
    ]
    if specific_nodes:
        nodes = specific_nodes
    nodes.sort(key=lambda x: len(x["title"]))

    documents = []
    seen = set()
    for node in nodes[:3]:
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


def _viewer_broad_business_web(rcept_no: str) -> list[str]:
    """Fetch only the broad '사업의 내용' parent as a fail-closed fallback.

    This is intentionally used only when narrow product/sales sections could
    not yield a coherent revenue mix. It helps companies whose segment tables
    are split across manufacturing/finance subsections without slowing normal
    successful requests.
    """
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

    nodes = _viewer_nodes(main.text)
    broad = [
        node for node in nodes
        if "사업의 내용" in node.get("title", "")
    ]
    broad.sort(key=lambda node: len(node.get("title", "")))
    for node in broad[:2]:
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
            if "매출" in response.text or "영업수익" in response.text:
                return [response.text]
        except requests.RequestException:
            continue
    return []


def _report_year(report: dict) -> int | None:
    name = report.get("reportName") or ""
    match = re.search(r"\((\d{4})\.", name)
    if match:
        return int(match.group(1))
    date = re.sub(r"[^0-9]", "", str(report.get("rceptDate") or ""))
    if len(date) >= 4:
        return int(date[:4]) - 1
    return None


def fetch_business_report(ticker: str, company_name: str = "", *,
                          force: bool = False, report_hint: dict | None = None) -> dict:
    code = _stock_code(ticker)
    cache_key = code
    bypass = os.environ.get("DART_STATIC_CACHE_BYPASS") == "1"
    if not force:
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
        if cached and (cached[1].get("available") or time.time() - cached[0] < NEGATIVE_CACHE_TTL):
            if cached[1].get("available") and time.time() - cached[0] >= REPORT_CHECK_TTL:
                _schedule_report_check(code, ticker, company_name, cached[1])
            return dict(cached[1], ticker=ticker)

        persistent = None if bypass else _load_persistent(code)
        static_cached = _static_business_context(code)
        if static_cached:
            static_cached["cacheMode"] = "static-precomputed"
        if persistent and static_cached and str(static_cached.get("rceptNo") or "") >= str(persistent[1].get("rceptNo") or ""):
            persistent = None
        if persistent or static_cached:
            checked_at, row = persistent if persistent else (0.0, static_cached)
            row = dict(row, ticker=ticker)
            if persistent:
                row["cacheMode"] = "render-key-value"
            with _CACHE_LOCK:
                _CACHE[cache_key] = (checked_at, row)
            if time.time() - checked_at >= REPORT_CHECK_TTL:
                _schedule_report_check(code, ticker, company_name, row)
            return row

    api_key = _clean(os.environ.get("DART_API_KEY"))
    report = report_hint
    documents: list[str] = []
    mode = "dart-web"
    try:
        if api_key and not report:
            report = _search_report_api(api_key, code)
        if report:
            # Content parsing starts only for a newly identified receipt.
            documents = _viewer_sections_web(report["rceptNo"])
            mode = "opendart-api" if report.get("mode") == "opendart-api" or api_key else "dart-web"
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
        if not mix:
            broad_documents = _viewer_broad_business_web(report["rceptNo"])
            if broad_documents:
                mix = extract_revenue_mix(broad_documents, year)
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
            "hasConsolidationAdjustment": mix.get("hasConsolidationAdjustment", False) if mix else False,
            "revenueBasis": mix.get("revenueBasis") if mix else None,
            "reason": None if mix else "revenue_breakdown_table_not_confident",
            "checkedAt": datetime.now(KST).isoformat(timespec="seconds"),
        }

    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.time(), result)
    if not bypass and result.get("available"):
        _save_persistent(code, result, time.time())
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
