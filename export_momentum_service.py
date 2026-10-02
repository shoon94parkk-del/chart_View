"""Official Korea Customs export-momentum API for Chart View Toss.

The browser never calls data.go.kr directly. This module keeps the public
service key server-side, normalizes XML into a stable JSON contract and reuses
a shared in-process cache for every user.
"""
from __future__ import annotations

import asyncio
import copy
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, HTTPException, Response

router = APIRouter()

TOTAL_URL = "https://apis.data.go.kr/1220000/Newtrade/getNewtradeList"
ITEM_URL = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
ITEM_COUNTRY_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"

CACHE_TTL_SEC = 60 * 60
REQUEST_TIMEOUT = (3.05, 12)
KST = ZoneInfo("Asia/Seoul")
_MONTH_RE = re.compile(r"^(\d{4})[.-]?(\d{2})$")

_CACHE: dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "refreshing": False,
    "lastError": None,
}
_CACHE_LOCK = asyncio.Lock()

# These are explicit HS proxies, not company-level exports and not MTI headline
# categories. Keeping that distinction visible prevents overclaiming.
ITEM_GROUPS = (
    {"name": "반도체", "codes": ("8541", "8542"), "note": "HS 8541+8542 합산"},
    {"name": "승용차", "codes": ("8703",), "note": "HS 8703 기준"},
    {"name": "석유제품", "codes": ("2710",), "note": "HS 2710 정제 석유제품 기준"},
    {"name": "화장품", "codes": ("3304",), "note": "HS 3304 미용·기초화장품 기준"},
    {"name": "선박", "codes": ("89",), "note": "HS 89 선박·보트류 기준"},
    {"name": "철강", "codes": ("72",), "note": "HS 72 철강 기준"},
)

COUNTRIES = (
    {"name": "미국", "code": "US"},
    {"name": "중국", "code": "CN"},
    {"name": "베트남", "code": "VN"},
    {"name": "일본", "code": "JP"},
    {"name": "대만", "code": "TW"},
)


class CustomsApiError(RuntimeError):
    pass


def service_key() -> str:
    """Return the configured data.go.kr key without exposing it to clients.

    Support the key name the user already saved plus the earlier generic names
    so a rename is not required for deployment.
    """
    for name in (
        "CUSTOMS_TOTAL_API_KEY",
        "DATA_GO_KR_SERVICE_KEY",
        "CUSTOMS_API_KEY",
        "CUSTOMS_SERVICE_KEY",
    ):
        raw = (os.environ.get(name) or "").strip()
        if raw:
            # data.go.kr may show either the encoded or decoded key. requests
            # should receive the decoded value and handle URL encoding once.
            return unquote(raw)
    return ""


def api_key_configured() -> bool:
    return bool(service_key())


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _month_shift(yyyymm: str, delta: int) -> str:
    year = int(yyyymm[:4])
    month = int(yyyymm[4:6])
    index = year * 12 + (month - 1) + delta
    return f"{index // 12:04d}{index % 12 + 1:02d}"


def _normalize_month(value: str | None) -> str | None:
    if not value:
        return None
    match = _MONTH_RE.match(str(value).strip())
    if not match:
        return None
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    return f"{match.group(1)}{month:02d}"


def _display_period(yyyymm: str) -> str:
    return f"{yyyymm[:4]}-{yyyymm[4:6]}"


def _pct(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return round((current / prior - 1.0) * 100.0, 1)


def _billion(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 1_000_000_000.0, 4)


def _parse_xml_payload(payload: bytes) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise CustomsApiError(f"관세청 XML 파싱 실패: {exc}") from exc

    result_code = (
        root.findtext(".//resultCode")
        or root.findtext(".//returnReasonCode")
        or root.findtext(".//returnAuthCode")
        or ""
    ).strip()
    result_msg = (
        root.findtext(".//resultMsg")
        or root.findtext(".//returnAuthMsg")
        or root.findtext(".//errMsg")
        or ""
    ).strip()

    if result_code and result_code not in {"00", "0"}:
        raise CustomsApiError(f"관세청 API 오류 {result_code}: {result_msg or '응답 오류'}")
    if result_msg and any(token in result_msg.upper() for token in (
        "SERVICE KEY", "SERVICE_KEY", "PERMISSION", "ACCESS DENIED", "NOT REGISTERED"
    )):
        raise CustomsApiError(f"관세청 API 인증 오류: {result_msg}")

    rows: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        row = {child.tag: (child.text or "").strip() for child in list(item)}
        if row:
            rows.append(row)
    return rows


def _request_rows(url: str, **params: str) -> list[dict[str, str]]:
    key = service_key()
    if not key:
        raise CustomsApiError(
            "Render 환경변수 CUSTOMS_TOTAL_API_KEY(또는 DATA_GO_KR_SERVICE_KEY)가 없습니다."
        )
    query = {"serviceKey": key, **params}
    response = requests.get(url, params=query, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return _parse_xml_payload(response.content)


def _total_months(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        month = _normalize_month(row.get("year"))
        if not month:
            continue
        exp = _number(row.get("expDlr"))
        imp = _number(row.get("impDlr"))
        bal = _number(row.get("balPayments"))
        if exp is None or imp is None:
            continue
        result[month] = {
            "exports": exp,
            "imports": imp,
            "balance": bal if bal is not None else exp - imp,
        }
    return result


def _fetch_total_history(end_yyyymm: str) -> dict[str, dict[str, float]]:
    current_start = _month_shift(end_yyyymm, -11)
    prior_end = _month_shift(end_yyyymm, -12)
    prior_start = _month_shift(end_yyyymm, -23)
    first = _request_rows(TOTAL_URL, strtYymm=prior_start, endYymm=prior_end)
    second = _request_rows(TOTAL_URL, strtYymm=current_start, endYymm=end_yyyymm)
    data = _total_months(first)
    data.update(_total_months(second))
    return data


def _hs_export(rows: list[dict[str, str]], requested: str, yyyymm: str) -> float | None:
    candidates = [
        row for row in rows
        if _normalize_month(row.get("year")) == yyyymm and _number(row.get("expDlr")) is not None
    ]
    if not candidates:
        return None

    exact = [row for row in candidates if str(row.get("hsCd") or "").strip() == requested]
    if exact:
        return sum(_number(row.get("expDlr")) or 0.0 for row in exact)

    prefixed = [
        row for row in candidates
        if str(row.get("hsCd") or "").strip().startswith(requested)
    ]
    if not prefixed:
        return None
    lengths = [len(str(row.get("hsCd") or "").strip()) for row in prefixed if row.get("hsCd")]
    if not lengths:
        return None
    shortest = min(lengths)
    by_code: dict[str, float] = {}
    for row in prefixed:
        code = str(row.get("hsCd") or "").strip()
        if len(code) != shortest:
            continue
        by_code[code] = max(by_code.get(code, 0.0), _number(row.get("expDlr")) or 0.0)
    return sum(by_code.values()) if by_code else None


def _fetch_hs_export(hs_code: str, yyyymm: str) -> float | None:
    rows = _request_rows(
        ITEM_URL,
        strtYymm=yyyymm,
        endYymm=yyyymm,
        hsSgn=hs_code,
    )
    return _hs_export(rows, hs_code, yyyymm)


def _country_export(rows: list[dict[str, str]], yyyymm: str) -> float | None:
    """Aggregate one country's export without double-counting HS hierarchy."""
    candidates = [
        row for row in rows
        if _normalize_month(row.get("year")) == yyyymm and _number(row.get("expDlr")) is not None
    ]
    if not candidates:
        return None

    aggregate = [
        row for row in candidates
        if not str(row.get("hsCd") or "").strip()
        or "총계" in str(row.get("statKor") or "")
    ]
    if aggregate:
        return max(_number(row.get("expDlr")) or 0.0 for row in aggregate)

    # When the API returns several HS hierarchy levels, summing every row would
    # double-count. Sum only the shortest available HS level (normally 2-digit).
    coded = []
    for row in candidates:
        code = str(row.get("hsCd") or "").strip()
        if code.isdigit():
            coded.append((code, _number(row.get("expDlr")) or 0.0))
    if not coded:
        return None
    shortest = min(len(code) for code, _ in coded)
    by_code: dict[str, float] = {}
    for code, value in coded:
        if len(code) == shortest:
            by_code[code] = max(by_code.get(code, 0.0), value)
    return sum(by_code.values()) if by_code else None


def _fetch_country_export(country_code: str, yyyymm: str) -> float | None:
    rows = _request_rows(
        ITEM_COUNTRY_URL,
        strtYymm=yyyymm,
        endYymm=yyyymm,
        cntyCd=country_code,
    )
    return _country_export(rows, yyyymm)


def _build_item(group: dict[str, Any], latest: str, prior: str) -> dict[str, Any] | None:
    current_values = [_fetch_hs_export(code, latest) for code in group["codes"]]
    prior_values = [_fetch_hs_export(code, prior) for code in group["codes"]]
    current = sum(value for value in current_values if value is not None)
    previous = sum(value for value in prior_values if value is not None)
    if not any(value is not None for value in current_values):
        return None
    return {
        "name": group["name"],
        "exportsUsdBillion": _billion(current),
        "exportYoY": _pct(current, previous if any(v is not None for v in prior_values) else None),
        "note": group["note"],
    }


def _build_country(country: dict[str, str], latest: str, prior: str) -> dict[str, Any] | None:
    current = _fetch_country_export(country["code"], latest)
    previous = _fetch_country_export(country["code"], prior)
    if current is None:
        return None
    return {
        "name": country["name"],
        "exportsUsdBillion": _billion(current),
        "exportYoY": _pct(current, previous),
        "note": f"관세청 국가코드 {country['code']} 기준",
    }


def _parallel_optional(builder, rows, latest: str, prior: str, workers: int = 6):
    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="customs-export") as pool:
        future_map = {pool.submit(builder, row, latest, prior): row for row in rows}
        for future in as_completed(future_map):
            row = future_map[future]
            try:
                value = future.result()
                if value:
                    results.append(value)
            except Exception as exc:
                errors.append(f"{row.get('name')}: {exc}")
    order = {row["name"]: idx for idx, row in enumerate(rows)}
    results.sort(key=lambda item: order.get(item.get("name"), 999))
    return results, errors


def _build_snapshot(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(KST)
    end_yyyymm = now.strftime("%Y%m")
    monthly = _fetch_total_history(end_yyyymm)
    if not monthly:
        raise CustomsApiError("관세청 수출입총괄 API가 월별 데이터를 반환하지 않았습니다.")

    latest = max(monthly)
    current = monthly[latest]
    prior = _month_shift(latest, -12)
    previous = monthly.get(prior, {})
    latest_year = latest[:4]

    ordered_months = sorted(monthly)
    recent = [month for month in ordered_months if month <= latest][-12:]
    history = []
    for month in recent:
        row = monthly[month]
        prior_row = monthly.get(_month_shift(month, -12), {})
        history.append({
            "period": _display_period(month),
            "exportsUsdBillion": _billion(row["exports"]),
            "exportYoY": _pct(row["exports"], prior_row.get("exports")),
        })

    cumulative_exports = sum(
        row["exports"] for month, row in monthly.items()
        if month.startswith(latest_year) and month <= latest
    )
    cumulative_balance = sum(
        row["balance"] for month, row in monthly.items()
        if month.startswith(latest_year) and month <= latest
    )

    items, item_errors = _parallel_optional(_build_item, ITEM_GROUPS, latest, prior)
    regions, region_errors = _parallel_optional(_build_country, COUNTRIES, latest, prior, workers=5)

    semiconductor = next((item for item in items if item["name"] == "반도체"), None)
    non_semi_yoy = None
    if semiconductor and previous.get("exports"):
        semi_current = (semiconductor.get("exportsUsdBillion") or 0.0) * 1_000_000_000.0
        # Re-query prior semiconductor only when the displayed group is available.
        try:
            semi_prior = sum(
                value or 0.0 for value in (_fetch_hs_export(code, prior) for code in ("8541", "8542"))
            )
            non_semi_yoy = _pct(
                current["exports"] - semi_current,
                previous["exports"] - semi_prior,
            )
        except Exception:
            non_semi_yoy = None

    updated = datetime.now(KST).isoformat()
    payload = {
        "schemaVersion": 2,
        "status": "official_api",
        "period": _display_period(latest),
        "periodLabel": f"{latest[:4]}년 {int(latest[4:6])}월",
        "publishedAt": None,
        "updatedAt": updated,
        "basis": "관세청 통관기준 월간 실적",
        "summary": {
            "exportsUsdBillion": _billion(current["exports"]),
            "importsUsdBillion": _billion(current["imports"]),
            "balanceUsdBillion": _billion(current["balance"]),
            "exportYoY": _pct(current["exports"], previous.get("exports")),
            "importYoY": _pct(current["imports"], previous.get("imports")),
            "cumulativeExportsUsdBillion": _billion(cumulative_exports),
            "cumulativeBalanceUsdBillion": _billion(cumulative_balance),
            "nonSemiconductorYoY": non_semi_yoy,
            "nonSemiconductorAndComputerYoY": None,
            "risingMajorItems": None,
            "majorItemCount": None,
        },
        "history": history,
        # The three monthly APIs do not provide 1~10/1~20-day preliminary rows.
        # Never manufacture checkpoints from monthly totals.
        "checkpoints": [],
        "items": items,
        "regions": regions,
        "sources": [
            {
                "name": "관세청 수출입총괄",
                "role": "월별 총수출·수입·무역수지",
                "url": "https://www.data.go.kr/data/15102108/openapi.do",
            },
            {
                "name": "관세청 품목별 수출입실적",
                "role": "HS 품목별 수출 실적",
                "url": "https://www.data.go.kr/data/15101609/openapi.do",
            },
            {
                "name": "관세청 품목별 국가별 수출입실적",
                "role": "국가별 수출 실적",
                "url": "https://www.data.go.kr/data/15100475/openapi.do",
            },
        ],
        "meta": {
            "provider": "Korea Customs Service / data.go.kr",
            "cacheTtlSec": CACHE_TTL_SEC,
            "itemMethod": "HS proxy groups",
            "regionMethod": "country totals aggregated at the shortest returned HS level",
            "warnings": item_errors[:3] + region_errors[:3],
        },
    }
    return payload


def _with_cache_meta(data: dict[str, Any], state: str) -> dict[str, Any]:
    result = copy.deepcopy(data)
    result.setdefault("meta", {})["cacheStatus"] = state
    if _CACHE.get("lastError"):
        result["meta"]["lastRefreshError"] = str(_CACHE["lastError"])[:240]
    return result


async def _refresh_cache() -> dict[str, Any]:
    async with _CACHE_LOCK:
        age = time.time() - float(_CACHE.get("timestamp") or 0.0)
        if _CACHE.get("data") is not None and age < CACHE_TTL_SEC:
            return _CACHE["data"]
        _CACHE["refreshing"] = True
        try:
            data = await asyncio.to_thread(_build_snapshot)
            _CACHE["data"] = data
            _CACHE["timestamp"] = time.time()
            _CACHE["lastError"] = None
            return data
        except Exception as exc:
            _CACHE["lastError"] = str(exc)
            raise
        finally:
            _CACHE["refreshing"] = False


async def _background_refresh() -> None:
    try:
        await _refresh_cache()
    except Exception as exc:
        print(f"[EXPORT_MOMENTUM] background refresh failed: {exc}")


async def warm_export_momentum() -> None:
    if not api_key_configured():
        print("[EXPORT_MOMENTUM] customs key not configured; skipping warm")
        return
    try:
        started = time.perf_counter()
        data = await _refresh_cache()
        print(
            f"[EXPORT_MOMENTUM] warm period={data.get('period')} "
            f"history={len(data.get('history') or [])} "
            f"items={len(data.get('items') or [])} "
            f"regions={len(data.get('regions') or [])} "
            f"elapsedMs={int((time.perf_counter()-started)*1000)}"
        )
    except Exception as exc:
        print(f"[EXPORT_MOMENTUM] warm failed: {exc}")


@router.get("/api/export-momentum")
async def export_momentum(response: Response):
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    data = _CACHE.get("data")
    age = time.time() - float(_CACHE.get("timestamp") or 0.0)

    if data is not None and age < CACHE_TTL_SEC:
        return _with_cache_meta(data, "fresh")

    if data is not None:
        if not _CACHE.get("refreshing"):
            asyncio.create_task(_background_refresh())
        return _with_cache_meta(data, "stale-revalidating")

    if not api_key_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CUSTOMS_API_KEY_MISSING",
                "message": "관세청 API 키가 Render 백엔드 환경변수에 설정되지 않았습니다.",
            },
        )

    try:
        data = await _refresh_cache()
        return _with_cache_meta(data, "fresh")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CUSTOMS_API_UNAVAILABLE",
                "message": str(exc)[:300],
            },
        ) from exc
