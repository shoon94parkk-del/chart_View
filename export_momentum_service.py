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

DETAIL_CACHE_TTL_SEC = 6 * 60 * 60
_DETAIL_CACHE: dict[str, dict[str, Any]] = {}
_DETAIL_CACHE_LOCK = asyncio.Lock()

# These are explicit HS proxies, not company-level exports and not MTI headline
# categories. Keeping that distinction visible prevents overclaiming.
ITEM_GROUPS = (
    {"key": "semiconductor", "name": "반도체", "codes": ("8541", "8542"), "note": "HS 8541+8542 합산"},
    {"key": "passenger-car", "name": "승용차", "codes": ("8703",), "note": "HS 8703 기준"},
    {"key": "petroleum", "name": "석유제품", "codes": ("2710",), "note": "HS 2710 정제 석유제품 기준"},
    {"key": "cosmetics", "name": "화장품", "codes": ("3304",), "note": "HS 3304 미용·기초화장품 기준"},
    {"key": "ships", "name": "선박", "codes": ("89",), "note": "HS 89 선박·보트류 기준"},
    {"key": "steel", "name": "철강", "codes": ("72",), "note": "HS 72 철강 기준"},
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


def _row_hs_code(row: dict[str, str]) -> str:
    # Itemtrade uses hsCode in some responses while nitemtrade uses hsCd.
    return str(row.get("hsCd") or row.get("hsCode") or "").strip()


def _month_rows(rows: list[dict[str, str]], yyyymm: str) -> list[dict[str, str]]:
    return [
        row for row in rows
        if _normalize_month(row.get("year")) == yyyymm and _number(row.get("expDlr")) is not None
    ]


def _fetch_item_rows(yyyymm: str) -> list[dict[str, str]]:
    # A prefix such as 8542 is not guaranteed to be accepted as hsSgn because
    # the provider commonly returns HSK 10-digit rows. Fetch one month once and
    # aggregate the desired prefixes locally instead of making one call per card.
    return _request_rows(ITEM_URL, strtYymm=yyyymm, endYymm=yyyymm)


def _find_item_period(latest: str, max_back: int = 3) -> tuple[str | None, list[dict[str, str]]]:
    for offset in range(max_back + 1):
        period = _month_shift(latest, -offset)
        rows = _fetch_item_rows(period)
        if _month_rows(rows, period):
            return period, rows
    return None, []


def _hs_prefix_metric(
    rows: list[dict[str, str]],
    requested: str,
    yyyymm: str,
    field: str,
) -> float | None:
    candidates = [
        row for row in _month_rows(rows, yyyymm)
        if _row_hs_code(row).startswith(requested) and _number(row.get(field)) is not None
    ]
    if not candidates:
        return None

    exact = [row for row in candidates if _row_hs_code(row) == requested]
    if exact:
        return sum(_number(row.get(field)) or 0.0 for row in exact)

    lengths = [len(_row_hs_code(row)) for row in candidates if _row_hs_code(row).isdigit()]
    if not lengths:
        return None
    aggregate_len = min(lengths)
    by_code: dict[str, float] = {}
    for row in candidates:
        code = _row_hs_code(row)
        if len(code) != aggregate_len:
            continue
        by_code[code] = max(by_code.get(code, 0.0), _number(row.get(field)) or 0.0)
    return sum(by_code.values()) if by_code else None


def _hs_prefix_export(rows: list[dict[str, str]], requested: str, yyyymm: str) -> float | None:
    return _hs_prefix_metric(rows, requested, yyyymm, "expDlr")


def _hs_prefix_weight(rows: list[dict[str, str]], requested: str, yyyymm: str) -> float | None:
    return _hs_prefix_metric(rows, requested, yyyymm, "expWgt")


def _hs_prefix_import(rows: list[dict[str, str]], requested: str, yyyymm: str) -> float | None:
    return _hs_prefix_metric(rows, requested, yyyymm, "impDlr")


def _hs_prefix_import_weight(rows: list[dict[str, str]], requested: str, yyyymm: str) -> float | None:
    return _hs_prefix_metric(rows, requested, yyyymm, "impWgt")


def _hs_prefix_balance(rows: list[dict[str, str]], requested: str, yyyymm: str) -> float | None:
    return _hs_prefix_metric(rows, requested, yyyymm, "balPayments")


def _unit_value_usd_per_kg(amount: float | None, weight: float | None) -> float | None:
    if amount is None or weight is None or weight <= 0:
        return None
    return round(amount / weight, 4)


def _build_items_from_rows(
    current_rows: list[dict[str, str]],
    prior_rows: list[dict[str, str]],
    period: str,
) -> list[dict[str, Any]]:
    prior = _month_shift(period, -12)
    results = []
    for group in ITEM_GROUPS:
        current_values = [_hs_prefix_export(current_rows, code, period) for code in group["codes"]]
        prior_values = [_hs_prefix_export(prior_rows, code, prior) for code in group["codes"]]
        current_weights = [_hs_prefix_weight(current_rows, code, period) for code in group["codes"]]
        prior_weights = [_hs_prefix_weight(prior_rows, code, prior) for code in group["codes"]]
        current_imports = [_hs_prefix_import(current_rows, code, period) for code in group["codes"]]
        prior_imports = [_hs_prefix_import(prior_rows, code, prior) for code in group["codes"]]
        current_import_weights = [_hs_prefix_import_weight(current_rows, code, period) for code in group["codes"]]
        current_balances = [_hs_prefix_balance(current_rows, code, period) for code in group["codes"]]
        if not any(value is not None for value in current_values):
            continue
        current = sum(value for value in current_values if value is not None)
        previous = sum(value for value in prior_values if value is not None)
        current_weight = sum(value for value in current_weights if value is not None)
        previous_weight = sum(value for value in prior_weights if value is not None)
        current_import = sum(value for value in current_imports if value is not None)
        previous_import = sum(value for value in prior_imports if value is not None)
        current_import_weight = sum(value for value in current_import_weights if value is not None)
        current_balance = sum(value for value in current_balances if value is not None)
        current_unit = _unit_value_usd_per_kg(
            current,
            current_weight if any(v is not None for v in current_weights) else None,
        )
        previous_unit = _unit_value_usd_per_kg(
            previous if any(v is not None for v in prior_values) else None,
            previous_weight if any(v is not None for v in prior_weights) else None,
        )
        results.append({
            "key": group["key"],
            "name": group["name"],
            "exportsUsdBillion": _billion(current),
            "exportYoY": _pct(current, previous if any(v is not None for v in prior_values) else None),
            "exportWeightKg": round(current_weight, 3) if any(v is not None for v in current_weights) else None,
            "exportWeightYoY": _pct(
                current_weight if any(v is not None for v in current_weights) else None,
                previous_weight if any(v is not None for v in prior_weights) else None,
            ),
            "unitValueUsdPerKg": current_unit,
            "unitValueYoY": _pct(current_unit, previous_unit),
            "importsUsdBillion": _billion(current_import) if any(v is not None for v in current_imports) else None,
            "importYoY": _pct(
                current_import if any(v is not None for v in current_imports) else None,
                previous_import if any(v is not None for v in prior_imports) else None,
            ),
            "importWeightKg": round(current_import_weight, 3) if any(v is not None for v in current_import_weights) else None,
            "tradeBalanceUsdBillion": _billion(current_balance) if any(v is not None for v in current_balances) else _billion(current - current_import),
            "note": group["note"],
        })
    return results


def _country_export(rows: list[dict[str, str]], yyyymm: str) -> float | None:
    """Return one country's export without double-counting HS hierarchy."""
    # nitemtrade includes a query-total row. For a single-month query this is
    # exactly the country total and avoids summing tens of thousands of HS rows.
    totals = [
        row for row in rows
        if str(row.get("year") or "").strip() == "총계" and _number(row.get("expDlr")) is not None
    ]
    if totals:
        return max(_number(row.get("expDlr")) or 0.0 for row in totals)

    candidates = _month_rows(rows, yyyymm)
    if not candidates:
        return None

    aggregate = [
        row for row in candidates
        if not _row_hs_code(row) or "총계" in str(row.get("statKor") or "")
    ]
    if aggregate:
        return max(_number(row.get("expDlr")) or 0.0 for row in aggregate)

    coded = []
    for row in candidates:
        code = _row_hs_code(row)
        if code.isdigit():
            coded.append((code, _number(row.get("expDlr")) or 0.0))
    if not coded:
        return None

    # Use only one hierarchy depth. If multiple levels are present, the
    # shortest level is already the broader aggregate and must not be added
    # again to its descendants.
    aggregate_len = min(len(code) for code, _ in coded)
    by_code: dict[str, float] = {}
    for code, value in coded:
        if len(code) == aggregate_len:
            by_code[code] = max(by_code.get(code, 0.0), value)
    return sum(by_code.values()) if by_code else None


def _fetch_country_rows(country_code: str, yyyymm: str) -> list[dict[str, str]]:
    return _request_rows(
        ITEM_COUNTRY_URL,
        strtYymm=yyyymm,
        endYymm=yyyymm,
        cntyCd=country_code,
    )


def _fetch_country_export(country_code: str, yyyymm: str) -> float | None:
    return _country_export(_fetch_country_rows(country_code, yyyymm), yyyymm)


def _find_region_period(latest: str, max_back: int = 3) -> str | None:
    # Use the U.S. as an availability probe; Customs monthly HS datasets are
    # published on the same cycle across countries.
    for offset in range(max_back + 1):
        period = _month_shift(latest, -offset)
        if _fetch_country_export("US", period) is not None:
            return period
    return None


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


def _item_group(key: str) -> dict[str, Any] | None:
    return next((group for group in ITEM_GROUPS if group["key"] == key), None)


def _fetch_item_range_rows(hs_code: str, start_yyyymm: str, end_yyyymm: str) -> list[dict[str, str]]:
    return _request_rows(
        ITEM_URL,
        strtYymm=start_yyyymm,
        endYymm=end_yyyymm,
        hsSgn=hs_code,
    )


def _fetch_group_range(group: dict[str, Any], start_yyyymm: str, end_yyyymm: str) -> dict[str, list[dict[str, str]]]:
    results: dict[str, list[dict[str, str]]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(group["codes"]) or 1), thread_name_prefix="customs-item-range") as pool:
        future_map = {
            pool.submit(_fetch_item_range_rows, code, start_yyyymm, end_yyyymm): code
            for code in group["codes"]
        }
        for future in as_completed(future_map):
            code = future_map[future]
            results[code] = future.result()
    return results


def _group_metric(
    rows_by_code: dict[str, list[dict[str, str]]],
    group: dict[str, Any],
    period: str,
    metric,
) -> float | None:
    values = [metric(rows_by_code.get(code, []), code, period) for code in group["codes"]]
    usable = [value for value in values if value is not None]
    return sum(usable) if usable else None


def _build_group_history(group: dict[str, Any], end_yyyymm: str) -> list[dict[str, Any]]:
    recent_start = _month_shift(end_yyyymm, -11)
    prior_end = _month_shift(end_yyyymm, -12)
    prior_start = _month_shift(end_yyyymm, -23)
    current_rows = _fetch_group_range(group, recent_start, end_yyyymm)
    prior_rows = _fetch_group_range(group, prior_start, prior_end)

    history = []
    for offset in range(-11, 1):
        period = _month_shift(end_yyyymm, offset)
        prior = _month_shift(period, -12)
        exports = _group_metric(current_rows, group, period, _hs_prefix_export)
        weight = _group_metric(current_rows, group, period, _hs_prefix_weight)
        imports = _group_metric(current_rows, group, period, _hs_prefix_import)
        import_weight = _group_metric(current_rows, group, period, _hs_prefix_import_weight)
        balance = _group_metric(current_rows, group, period, _hs_prefix_balance)
        prior_exports = _group_metric(prior_rows, group, prior, _hs_prefix_export)
        prior_weight = _group_metric(prior_rows, group, prior, _hs_prefix_weight)
        prior_imports = _group_metric(prior_rows, group, prior, _hs_prefix_import)

        unit_value = _unit_value_usd_per_kg(exports, weight)
        prior_unit_value = _unit_value_usd_per_kg(prior_exports, prior_weight)
        if exports is None:
            continue
        history.append({
            "period": _display_period(period),
            "exportsUsdBillion": _billion(exports),
            "exportYoY": _pct(exports, prior_exports),
            "exportWeightKg": round(weight, 3) if weight is not None else None,
            "exportWeightYoY": _pct(weight, prior_weight),
            "unitValueUsdPerKg": unit_value,
            "unitValueYoY": _pct(unit_value, prior_unit_value),
            "importsUsdBillion": _billion(imports),
            "importYoY": _pct(imports, prior_imports),
            "importWeightKg": round(import_weight, 3) if import_weight is not None else None,
            "tradeBalanceUsdBillion": _billion(balance if balance is not None else ((exports or 0) - (imports or 0))),
        })
    return history


def _fetch_country_item_export(country: dict[str, str], group: dict[str, Any], period: str) -> dict[str, Any] | None:
    total = 0.0
    found = False
    for code in group["codes"]:
        rows = _request_rows(
            ITEM_COUNTRY_URL,
            strtYymm=period,
            endYymm=period,
            hsSgn=code,
            cntyCd=country["code"],
        )
        value = _country_export(rows, period)
        if value is not None:
            total += value
            found = True
    if not found:
        return None
    return {
        "name": country["name"],
        "code": country["code"],
        "exportsUsdBillion": _billion(total),
    }


def _build_country_item_breakdown(group: dict[str, Any], period: str, total_exports: float | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="customs-country-item") as pool:
        future_map = {
            pool.submit(_fetch_country_item_export, country, group, period): country
            for country in COUNTRIES
        }
        for future in as_completed(future_map):
            value = future.result()
            if value:
                exports = (value.get("exportsUsdBillion") or 0.0) * 1_000_000_000.0
                value["sharePct"] = round(exports / total_exports * 100.0, 1) if total_exports and total_exports > 0 else None
                rows.append(value)
    order = {country["code"]: idx for idx, country in enumerate(COUNTRIES)}
    rows.sort(key=lambda row: order.get(row["code"], 999))
    return rows


def _build_item_detail(key: str) -> dict[str, Any]:
    group = _item_group(key)
    if not group:
        raise KeyError(key)

    snapshot = _CACHE.get("data")
    period = None
    if snapshot:
        raw_period = snapshot.get("itemPeriod")
        period = raw_period.replace("-", "") if raw_period else None
    if not period:
        period = _month_shift(datetime.now(KST).strftime("%Y%m"), -2)

    history = _build_group_history(group, period)
    if not history:
        raise CustomsApiError(f"{group['name']} 12개월 상세 데이터를 반환하지 않았습니다.")
    latest = history[-1]
    total_exports = (latest.get("exportsUsdBillion") or 0.0) * 1_000_000_000.0
    countries = _build_country_item_breakdown(group, period, total_exports)

    return {
        "schemaVersion": 1,
        "key": group["key"],
        "name": group["name"],
        "note": group["note"],
        "period": _display_period(period),
        "history": history,
        "countries": countries,
        "meta": {
            "provider": "Korea Customs Service / data.go.kr",
            "countryScope": "US, CN, VN, JP, TW configured major markets; not a global top-country ranking",
            "unitValueMethod": "export 신고미화금액 / 순중량(kg)",
            "cacheTtlSec": DETAIL_CACHE_TTL_SEC,
        },
    }


async def _refresh_item_detail(key: str) -> dict[str, Any]:
    async with _DETAIL_CACHE_LOCK:
        cached = _DETAIL_CACHE.get(key)
        if cached and time.time() - float(cached.get("timestamp") or 0.0) < DETAIL_CACHE_TTL_SEC:
            return cached["data"]
        data = await asyncio.to_thread(_build_item_detail, key)
        _DETAIL_CACHE[key] = {"data": data, "timestamp": time.time(), "lastError": None}
        return data


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
    # The total-trade endpoint may expose current-month partial customs
    # receipts, while the item/country endpoints are monthly statistics that
    # are maintained through the previous completed month. Keep the dashboard
    # on a comparable full-month basis and never mix MTD totals with monthly
    # item/country figures.
    end_yyyymm = _month_shift(now.strftime("%Y%m"), -1)
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

    item_errors: list[str] = []
    item_period = None
    items: list[dict[str, Any]] = []
    try:
        item_period, item_rows = _find_item_period(latest)
        if item_period:
            prior_item_rows = _fetch_item_rows(_month_shift(item_period, -12))
            items = _build_items_from_rows(item_rows, prior_item_rows, item_period)
    except Exception as exc:
        item_errors.append(f"품목 데이터: {exc}")

    region_errors: list[str] = []
    region_period = None
    regions: list[dict[str, Any]] = []
    try:
        region_period = _find_region_period(latest)
        if region_period:
            regions, region_errors = _parallel_optional(
                _build_country,
                COUNTRIES,
                region_period,
                _month_shift(region_period, -12),
                workers=5,
            )
    except Exception as exc:
        region_errors.append(f"국가 데이터: {exc}")

    # A non-semiconductor total is only comparable when the HS detail month is
    # the same month as the headline total. Do not mix September totals with
    # August HS detail merely to fill a card.
    non_semi_yoy = None
    semiconductor = next((item for item in items if item["name"] == "반도체"), None)
    if item_period == latest and semiconductor and previous.get("exports"):
        semi_current = (semiconductor.get("exportsUsdBillion") or 0.0) * 1_000_000_000.0
        semi_prior = sum(
            _hs_prefix_export(prior_item_rows, code, _month_shift(item_period, -12)) or 0.0
            for code in ("8541", "8542")
        )
        non_semi_yoy = _pct(
            current["exports"] - semi_current,
            previous["exports"] - semi_prior,
        )

    updated = datetime.now(KST).isoformat()
    payload = {
        "schemaVersion": 3,
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
        "itemPeriod": _display_period(item_period) if item_period else None,
        "regionPeriod": _display_period(region_period) if region_period else None,
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
            "itemMethod": "HS proxy groups; export value + net weight + implied USD/kg unit value",
            "regionMethod": "single-month country query total; HS detail fallback without hierarchy double count",
            "detailLagMonths": {
                "items": ((int(latest[:4]) * 12 + int(latest[4:6])) - (int(item_period[:4]) * 12 + int(item_period[4:6]))) if item_period else None,
                "regions": ((int(latest[:4]) * 12 + int(latest[4:6])) - (int(region_period[:4]) * 12 + int(region_period[4:6]))) if region_period else None,
            },
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
        warnings = (data.get("meta") or {}).get("warnings") or []
        print(
            f"[EXPORT_MOMENTUM] warm period={data.get('period')} "
            f"history={len(data.get('history') or [])} "
            f"items={len(data.get('items') or [])}@{data.get('itemPeriod')} "
            f"regions={len(data.get('regions') or [])}@{data.get('regionPeriod')} "
            f"warnings={len(warnings)} "
            f"elapsedMs={int((time.perf_counter()-started)*1000)}"
        )
        for warning in warnings[:3]:
            print(f"[EXPORT_MOMENTUM] warning: {warning}")
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


@router.get("/api/export-momentum/item-detail")
async def export_momentum_item_detail(key: str, response: Response):
    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=21600"
    group = _item_group(key)
    if not group:
        raise HTTPException(
            status_code=404,
            detail={"code": "EXPORT_ITEM_NOT_FOUND", "message": "지원하지 않는 수출 품목입니다."},
        )
    cached = _DETAIL_CACHE.get(key)
    if cached and time.time() - float(cached.get("timestamp") or 0.0) < DETAIL_CACHE_TTL_SEC:
        result = copy.deepcopy(cached["data"])
        result.setdefault("meta", {})["cacheStatus"] = "fresh"
        return result
    try:
        data = await _refresh_item_detail(key)
        result = copy.deepcopy(data)
        result.setdefault("meta", {})["cacheStatus"] = "fresh"
        return result
    except Exception as exc:
        if cached and cached.get("data"):
            result = copy.deepcopy(cached["data"])
            result.setdefault("meta", {})["cacheStatus"] = "stale-error"
            result["meta"]["lastRefreshError"] = str(exc)[:240]
            return result
        raise HTTPException(
            status_code=503,
            detail={"code": "EXPORT_ITEM_DETAIL_UNAVAILABLE", "message": str(exc)[:300]},
        ) from exc
