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
TEN_DAY_EXPORT_URL = "https://apis.data.go.kr/1220000/prlstMmUtPrviExpAcrs/getPrlstMmUtPrviExpAcrs"

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

PROVISIONAL_CACHE_TTL_SEC = 30 * 60
_PROVISIONAL_CACHE: dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "lastError": None,
}
_PROVISIONAL_CACHE_LOCK = asyncio.Lock()

SEMICONDUCTOR_COUNTRY_CACHE_TTL_SEC = 12 * 60 * 60
_SEMICONDUCTOR_COUNTRY_CACHE: dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "lastError": None,
}
_SEMICONDUCTOR_COUNTRY_LOCK = asyncio.Lock()

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

SEMICONDUCTOR_SEGMENTS = (
    {
        "key": "memory-total",
        "name": "메모리 IC",
        "code": "854232",
        "group": "memory",
        "note": "HS 854232 메모리 전체",
    },
    {
        "key": "dram",
        "name": "DRAM",
        "code": "8542321010",
        "group": "memory",
        "note": "HSK 8542321010 · HBM은 별도 HSK 코드가 없어 독립 집계 불가",
    },
    {
        "key": "flash",
        "name": "Flash memory",
        "code": "8542321030",
        "group": "memory",
        "note": "HSK 8542321030 · NAND/NOR 등을 포함하는 Flash memory 분류",
    },
    {
        "key": "sram",
        "name": "SRAM",
        "code": "8542321020",
        "group": "memory",
        "note": "HSK 8542321020",
    },
    {
        "key": "mcp-memory",
        "name": "MCP",
        "code": "8542323000",
        "group": "memory",
        "note": "HSK 8542323000 · 복합구조칩 메모리(Multichip integrated circuits)",
    },
    {
        "key": "dram-module",
        "name": "DRAM 모듈",
        "code": "8473304060",
        "group": "module",
        "note": "HSK 8473304060 · DRAM modules",
    },
    {
        "key": "processor-controller",
        "name": "프로세서·컨트롤러",
        "code": "854231",
        "group": "logic",
        "note": "HS 854231",
    },
    {
        "key": "other-ic",
        "name": "기타 IC",
        "code": "854239",
        "group": "logic",
        "note": "HS 854239",
    },
)

SEMICONDUCTOR_REPORT_KEYS = (
    "memory-total",
    "dram",
    "flash",
    "mcp-memory",
    "dram-module",
)


COUNTRIES = (
    {"name": "미국", "code": "US"},
    {"name": "중국", "code": "CN"},
    {"name": "베트남", "code": "VN"},
    {"name": "일본", "code": "JP"},
    {"name": "대만", "code": "TW"},
)

TEN_DAY_EXPORT_FIELDS = (
    ("itemUsdAmt00", "total", "전체"),
    ("itemUsdAmt01", "semiconductor", "반도체"),
    ("itemUsdAmt02", "steel", "철강제품"),
    ("itemUsdAmt03", "passenger-car", "승용차"),
    ("itemUsdAmt04", "petroleum", "석유제품"),
    ("itemUsdAmt05", "wireless", "무선통신기기"),
    ("itemUsdAmt06", "ships", "선박"),
    ("itemUsdAmt07", "auto-parts", "자동차부품"),
    ("itemUsdAmt08", "computer-peripherals", "컴퓨터주변기기"),
    ("itemUsdAmt09", "precision", "정밀기기"),
    ("itemUsdAmt10", "appliances", "가전제품"),
)

SEMICONDUCTOR_COUNTRY_SEGMENT_KEYS = (
    "dram",
    "flash",
    "mcp-memory",
    "dram-module",
)

SEMICONDUCTOR_COUNTRY_MARKETS = (
    {"name": "중국", "code": "CN"},
    {"name": "홍콩", "code": "HK"},
    {"name": "베트남", "code": "VN"},
    {"name": "대만", "code": "TW"},
    {"name": "미국", "code": "US"},
    {"name": "일본", "code": "JP"},
)

HS2_NAMES = {
    "27": "광물성 연료·석유",
    "29": "유기화학품",
    "30": "의약품",
    "33": "화장품·향료",
    "38": "각종 화학공업 생산품",
    "39": "플라스틱",
    "40": "고무제품",
    "48": "종이·판지",
    "61": "편물 의류",
    "62": "비편물 의류",
    "72": "철강",
    "73": "철강제품",
    "74": "구리",
    "76": "알루미늄",
    "84": "기계류",
    "85": "전기기기·전자부품",
    "87": "자동차·차량",
    "89": "선박·보트",
    "90": "광학·정밀기기",
    "94": "가구·조명",
}


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


def _item_period_available(period: str) -> bool:
    """Probe a lightweight, consistently traded HSK before fetching the full month."""
    rows = _request_rows(
        ITEM_URL,
        strtYymm=period,
        endYymm=period,
        hsSgn="8542321010",
    )
    return bool(_month_rows(rows, period))


def _find_item_period_candidate(latest: str, max_back: int = 3) -> str | None:
    for offset in range(max_back + 1):
        period = _month_shift(latest, -offset)
        try:
            if _item_period_available(period):
                return period
        except Exception as exc:
            print(f"[EXPORT_MOMENTUM] item period probe {period} failed: {exc}")
    return None


def _find_item_period(latest: str, max_back: int = 3) -> tuple[str | None, list[dict[str, str]]]:
    """Compatibility wrapper for tests/callers that need period + full rows."""
    period = _find_item_period_candidate(latest, max_back=max_back)
    if not period:
        return None, []
    return period, _fetch_item_rows(period)


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


def _hs2_codes(rows: list[dict[str, str]], period: str) -> list[str]:
    codes = set()
    for row in _month_rows(rows, period):
        code = _row_hs_code(row)
        if len(code) >= 2 and code[:2].isdigit():
            number = int(code[:2])
            if 1 <= number <= 97:
                codes.add(code[:2])
    return sorted(codes)


def _hs2_name(rows: list[dict[str, str]], code: str, period: str) -> str:
    exact = [
        row for row in _month_rows(rows, period)
        if _row_hs_code(row) == code and str(row.get("statKor") or "").strip()
    ]
    if exact:
        return str(exact[0].get("statKor") or "").strip()
    return HS2_NAMES.get(code, f"HS {code}")


def _build_hs2_breadth(
    current_rows: list[dict[str, str]],
    prior_rows: list[dict[str, str]],
    period: str,
) -> dict[str, Any]:
    prior = _month_shift(period, -12)
    codes = sorted(set(_hs2_codes(current_rows, period)) | set(_hs2_codes(prior_rows, prior)))
    movers: list[dict[str, Any]] = []

    for code in codes:
        current = _hs_prefix_export(current_rows, code, period)
        previous = _hs_prefix_export(prior_rows, code, prior)
        if current is None and previous is None:
            continue
        current = current or 0.0
        previous = previous or 0.0
        delta = current - previous
        movers.append({
            "code": code,
            "name": _hs2_name(current_rows, code, period),
            "exportsUsdBillion": _billion(current),
            "priorExportsUsdBillion": _billion(previous),
            "deltaUsdBillion": _billion(delta),
            "exportYoY": _pct(current, previous),
        })

    current_total = sum((row["exportsUsdBillion"] or 0.0) for row in movers)
    prior_total = sum((row["priorExportsUsdBillion"] or 0.0) for row in movers)
    comparable = [row for row in movers if row["priorExportsUsdBillion"] and row["priorExportsUsdBillion"] > 0]
    rising = [row for row in comparable if (row["exportYoY"] or 0.0) > 0.1]
    falling = [row for row in comparable if (row["exportYoY"] or 0.0) < -0.1]
    flat = [row for row in comparable if -0.1 <= (row["exportYoY"] or 0.0) <= 0.1]

    for row in movers:
        row["sharePct"] = round((row["exportsUsdBillion"] or 0.0) / current_total * 100.0, 1) if current_total > 0 else None

    rising_export = sum((row["exportsUsdBillion"] or 0.0) for row in rising)
    return {
        "period": _display_period(period),
        "level": "HS2",
        "comparableCount": len(comparable),
        "risingCount": len(rising),
        "fallingCount": len(falling),
        "flatCount": len(flat),
        "risingBreadthPct": round(len(rising) / len(comparable) * 100.0, 1) if comparable else None,
        "risingExportSharePct": round(rising_export / current_total * 100.0, 1) if current_total > 0 else None,
        "netChangeUsdBillion": round(current_total - prior_total, 4),
        "topPositive": sorted(
            [row for row in movers if (row["deltaUsdBillion"] or 0.0) > 0],
            key=lambda row: row["deltaUsdBillion"] or 0.0,
            reverse=True,
        )[:6],
        "topNegative": sorted(
            [row for row in movers if (row["deltaUsdBillion"] or 0.0) < 0],
            key=lambda row: row["deltaUsdBillion"] or 0.0,
        )[:6],
    }


def _avg(values: list[float | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 1)


def _momentum_label(avg3: float | None, acceleration: float | None) -> str:
    if avg3 is None:
        return "데이터 부족"
    if acceleration is None:
        return "3개월 평균"
    if avg3 > 0 and acceleration > 0:
        return "증가세 강화"
    if avg3 > 0 and acceleration < 0:
        return "증가세 둔화"
    if avg3 < 0 and acceleration > 0:
        return "감소폭 축소"
    if avg3 < 0 and acceleration < 0:
        return "감소세 확대"
    return "보합"


def _phase_label(weight_yoy: float | None, unit_yoy: float | None) -> str:
    if weight_yoy is None or unit_yoy is None:
        return "데이터 부족"
    if weight_yoy > 0 and unit_yoy > 0:
        return "물량↑·단위가치↑"
    if weight_yoy < 0 and unit_yoy > 0:
        return "물량↓·단위가치↑"
    if weight_yoy < 0 and unit_yoy < 0:
        return "물량↓·단위가치↓"
    if weight_yoy > 0 and unit_yoy < 0:
        return "물량↑·단위가치↓"
    return "혼조·보합"


def _build_momentum_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        "exports": "exportYoY",
        "volume": "exportWeightYoY",
        "unitValue": "unitValueYoY",
    }
    result: dict[str, Any] = {}
    for key, field in metrics.items():
        last3 = [row.get(field) for row in history[-3:]]
        prev3 = [row.get(field) for row in history[-6:-3]]
        avg3 = _avg(last3)
        prior_avg3 = _avg(prev3)
        acceleration = round(avg3 - prior_avg3, 1) if avg3 is not None and prior_avg3 is not None else None
        result[key] = {
            "avg3mYoY": avg3,
            "previous3mYoY": prior_avg3,
            "accelerationPp": acceleration,
            "label": _momentum_label(avg3, acceleration),
        }

    phase_history = []
    for row in history:
        phase_history.append({
            "period": row.get("period"),
            "phase": _phase_label(row.get("exportWeightYoY"), row.get("unitValueYoY")),
            "volumeYoY": row.get("exportWeightYoY"),
            "unitValueYoY": row.get("unitValueYoY"),
        })
    result["phaseHistory"] = phase_history
    result["latestPhase"] = phase_history[-1]["phase"] if phase_history else "데이터 부족"
    return result


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


def _fetch_semiconductor_previous_month_rows(period: str) -> list[dict[str, str]]:
    """Fetch only the report HSK rows needed for month-over-month comparison.

    A full unfiltered Itemtrade month is expensive. The latest/prior-year full
    tables are already needed for the broader export dashboard, but MoM only
    needs five semiconductor report segments. Query those codes in parallel.
    """
    segments = [row for row in SEMICONDUCTOR_SEGMENTS if row["key"] in SEMICONDUCTOR_REPORT_KEYS]
    rows: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=len(segments), thread_name_prefix="customs-semi-mom") as pool:
        future_map = {
            pool.submit(
                _request_rows,
                ITEM_URL,
                strtYymm=period,
                endYymm=period,
                hsSgn=segment["code"],
            ): segment
            for segment in segments
        }
        for future in as_completed(future_map):
            segment = future_map[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                # MoM is an enrichment; do not take down the full export
                # snapshot when one targeted segment query is unavailable.
                print(f"[EXPORT_MOMENTUM] semiconductor MoM {segment['key']} failed: {exc}")
    return rows


def _build_semiconductor_breakdown_from_rows(
    current_rows: list[dict[str, str]],
    prior_rows: list[dict[str, str]],
    previous_month_rows: list[dict[str, str]],
    period: str,
) -> list[dict[str, Any]]:
    """Build latest semiconductor HSK detail from already-fetched monthly rows.

    This intentionally performs no provider I/O. The main export snapshot has
    already fetched the complete item table for the latest detail month and its
    prior-year comparison month, so reuse those rows instead of fanning out
    extra HSK requests when a user opens semiconductor detail.
    """
    prior = _month_shift(period, -12)
    previous_month = _month_shift(period, -1)
    results: list[dict[str, Any]] = []
    for segment in SEMICONDUCTOR_SEGMENTS:
        code = segment["code"]
        exports = _hs_prefix_export(current_rows, code, period)
        previous = _hs_prefix_export(prior_rows, code, prior)
        previous_month_exports = _hs_prefix_export(previous_month_rows, code, previous_month)
        weight = _hs_prefix_weight(current_rows, code, period)
        prior_weight = _hs_prefix_weight(prior_rows, code, prior)
        previous_month_weight = _hs_prefix_weight(previous_month_rows, code, previous_month)
        if exports is None:
            continue
        unit_value = _unit_value_usd_per_kg(exports, weight)
        prior_unit_value = _unit_value_usd_per_kg(previous, prior_weight)
        previous_month_unit_value = _unit_value_usd_per_kg(previous_month_exports, previous_month_weight)
        results.append({
            "key": segment["key"],
            "name": segment["name"],
            "code": code,
            "group": segment["group"],
            "note": segment["note"],
            "period": _display_period(period),
            "exportsUsdBillion": _billion(exports),
            "exportYoY": _pct(exports, previous),
            "exportMoM": _pct(exports, previous_month_exports),
            "exportWeightKg": round(weight, 3) if weight is not None else None,
            "exportWeightYoY": _pct(weight, prior_weight),
            "exportWeightMoM": _pct(weight, previous_month_weight),
            "unitValueUsdPerKg": unit_value,
            "unitValueYoY": _pct(unit_value, prior_unit_value),
            "unitValueMoM": _pct(unit_value, previous_month_unit_value),
            "history": [],
        })
    return results


def _ten_day_stage(row: dict[str, str]) -> int | None:
    raw = str(row.get("priodDt") or "").strip()
    if not raw:
        return None
    match = re.search(r"(?:01|1)\s*[~\-]\s*(10|20|2[89]|30|31)", raw)
    if match:
        day = int(match.group(1))
        return 10 if day <= 10 else 20 if day <= 20 else 30
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 8:
        day = int(digits[-2:])
        return 10 if day <= 10 else 20 if day <= 20 else 30
    return None


def _ten_day_stage_label(stage: int) -> str:
    return "1~10일" if stage == 10 else "1~20일" if stage == 20 else "월 전체"


def _ten_day_amount_billion(row: dict[str, str], field: str) -> float | None:
    value = _number(row.get(field))
    if value is None:
        return None
    # Provider contract unit: USD thousand -> USD billion.
    return round(value / 1_000_000.0, 4)


def _fetch_ten_day_rows(start_yyyymm: str, end_yyyymm: str) -> list[dict[str, str]]:
    return _request_rows(
        TEN_DAY_EXPORT_URL,
        strtYymm=start_yyyymm,
        endYymm=end_yyyymm,
    )


def _ten_day_month_map(rows: list[dict[str, str]]) -> dict[str, dict[int, dict[str, str]]]:
    result: dict[str, dict[int, dict[str, str]]] = {}
    for row in rows:
        month = _normalize_month(row.get("priodMon"))
        stage = _ten_day_stage(row)
        if not month or stage is None:
            continue
        result.setdefault(month, {})[stage] = row
    return result


def _quantile(values: list[float], q: float) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * min(1.0, max(0.0, q))
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    fraction = position - lower
    return clean[lower] * (1.0 - fraction) + clean[upper] * fraction


def _completion_ratios(
    month_map: dict[str, dict[int, dict[str, str]]],
    field: str,
    stage: int,
    before_month: str,
    max_months: int = 60,
) -> list[tuple[str, float]]:
    ratios: list[tuple[str, float]] = []
    for month in sorted((key for key in month_map if key < before_month), reverse=True):
        rows = month_map.get(month, {})
        stage_row = rows.get(stage)
        final_row = rows.get(30)
        if not stage_row or not final_row:
            continue
        partial = _ten_day_amount_billion(stage_row, field)
        final = _ten_day_amount_billion(final_row, field)
        if partial is None or final is None or partial <= 0 or final <= 0:
            continue
        ratio = partial / final
        if 0.05 <= ratio <= 1.5:
            ratios.append((month, ratio))
        if len(ratios) >= max_months:
            break
    ratios.reverse()
    return ratios


def _landing_backtest(
    month_map: dict[str, dict[int, dict[str, str]]],
    field: str,
    stage: int,
    before_month: str,
    max_targets: int = 24,
) -> dict[str, Any]:
    candidates = [
        month for month in sorted(month_map)
        if month < before_month and stage in month_map.get(month, {}) and 30 in month_map.get(month, {})
    ]
    results: list[dict[str, float]] = []
    for target in candidates:
        history = _completion_ratios(month_map, field, stage, target, max_months=60)
        ratios = [ratio for _, ratio in history]
        if len(ratios) < 12:
            continue
        median = _quantile(ratios, 0.5)
        q25 = _quantile(ratios, 0.25)
        q75 = _quantile(ratios, 0.75)
        partial = _ten_day_amount_billion(month_map[target][stage], field)
        actual = _ten_day_amount_billion(month_map[target][30], field)
        if None in (median, q25, q75, partial, actual) or not actual:
            continue
        estimate = partial / median
        lower = partial / q75
        upper = partial / q25
        results.append({
            "absErrorPct": abs(estimate / actual - 1.0) * 100.0,
            "inRange": 1.0 if lower <= actual <= upper else 0.0,
        })
    results = results[-max_targets:]
    if not results:
        return {
            "sampleCount": 0,
            "medianAbsErrorPct": None,
            "rangeHitPct": None,
        }
    errors = [row["absErrorPct"] for row in results]
    return {
        "sampleCount": len(results),
        "medianAbsErrorPct": round(_quantile(errors, 0.5) or 0.0, 1),
        "rangeHitPct": round(sum(row["inRange"] for row in results) / len(results) * 100.0, 1),
    }


def _landing_projection_metric(
    month_map: dict[str, dict[int, dict[str, str]]],
    month: str,
    stage: int,
    field: str,
    *,
    actual_if_known: bool,
) -> dict[str, Any] | None:
    current_rows = month_map.get(month, {})
    stage_row = current_rows.get(stage)
    if not stage_row:
        return None
    current = _ten_day_amount_billion(stage_row, field)
    if current is None or current <= 0:
        return None

    history = _completion_ratios(month_map, field, stage, month, max_months=60)
    ratios = [ratio for _, ratio in history]
    if len(ratios) < 12:
        return None
    q25 = _quantile(ratios, 0.25)
    median = _quantile(ratios, 0.5)
    q75 = _quantile(ratios, 0.75)
    if None in (q25, median, q75) or min(q25, median, q75) <= 0:
        return None

    estimate = current / median
    lower = current / q75
    upper = current / q25
    prior_final = _ten_day_amount_billion(
        month_map.get(_month_shift(month, -12), {}).get(30, {}),
        field,
    )
    backtest = _landing_backtest(month_map, field, stage, month)
    actual = _ten_day_amount_billion(current_rows.get(30, {}), field) if actual_if_known else None

    return {
        "currentUsdBillion": round(current, 4),
        "estimateUsdBillion": round(estimate, 4),
        "rangeLowUsdBillion": round(lower, 4),
        "rangeHighUsdBillion": round(upper, 4),
        "medianCompletionPct": round(median * 100.0, 1),
        "completionQ25Pct": round(q25 * 100.0, 1),
        "completionQ75Pct": round(q75 * 100.0, 1),
        "projectedYoY": _pct(estimate, prior_final),
        "rangeYoYLow": _pct(lower, prior_final),
        "rangeYoYHigh": _pct(upper, prior_final),
        "historySampleCount": len(ratios),
        "backtest": backtest,
        "actualUsdBillion": round(actual, 4) if actual is not None else None,
        "actualErrorPct": round((estimate / actual - 1.0) * 100.0, 1) if actual else None,
    }


def _build_landing_projection(
    month_map: dict[str, dict[int, dict[str, str]]],
    month: str,
) -> dict[str, Any] | None:
    rows = month_map.get(month, {})
    if not rows:
        return None
    latest_stage = max(rows)
    is_final = 30 in rows
    stage = 20 if is_final and 20 in rows else 10 if is_final and 10 in rows else latest_stage
    if stage not in (10, 20):
        return {
            "status": "final",
            "stage": 30,
            "stageLabel": "월 전체",
            "message": "월말 잠정치가 발표되어 착지 추정 대신 실제 마감값을 표시합니다.",
            "total": None,
            "semiconductor": None,
        }

    total = _landing_projection_metric(
        month_map, month, stage, "itemUsdAmt00", actual_if_known=is_final
    )
    semiconductor = _landing_projection_metric(
        month_map, month, stage, "itemUsdAmt01", actual_if_known=is_final
    )
    return {
        "status": "final-review" if is_final else "open",
        "stage": stage,
        "stageLabel": _ten_day_stage_label(stage),
        "message": (
            "월말 잠정치가 발표되어 당시 체크포인트 추정과 실제 마감값을 비교합니다."
            if is_final else
            "과거 같은 단계의 월말 완성률 분포로 계산한 통계적 착지 범위입니다."
        ),
        "total": total,
        "semiconductor": semiconductor,
        "model": {
            "historyWindowMonths": 60,
            "range": "completion ratio 25th–75th percentile",
            "backtestWindowMonths": 24,
            "minimumHistorySamples": 12,
        },
    }


def _ten_day_metric_row(
    row: dict[str, str],
    prior_row: dict[str, str] | None,
    previous_month_row: dict[str, str] | None,
    field: str,
) -> dict[str, Any]:
    current = _ten_day_amount_billion(row, field)
    prior = _ten_day_amount_billion(prior_row or {}, field)
    previous_month = _ten_day_amount_billion(previous_month_row or {}, field)
    return {
        "exportsUsdBillion": current,
        "exportYoY": _pct(current, prior),
        "exportMoM": _pct(current, previous_month),
        "priorYearUsdBillion": prior,
        "previousMonthUsdBillion": previous_month,
        "deltaYoYUsdBillion": round(current - prior, 4) if current is not None and prior is not None else None,
    }


def _build_provisional_radar(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(KST)
    query_end = now.strftime("%Y%m")
    # The 10-day API payload is compact. Keep six years so the landing model
    # has enough history for rolling completion ratios and out-of-sample backtests.
    query_start = _month_shift(query_end, -71)
    rows = _fetch_ten_day_rows(query_start, query_end)
    month_map = _ten_day_month_map(rows)
    if not month_map:
        raise CustomsApiError("관세청 10일 단위 잠정치 API가 데이터를 반환하지 않았습니다.")

    latest_month = max(month_map)
    current_month = month_map[latest_month]
    prior_month_key = _month_shift(latest_month, -12)
    previous_month_key = _month_shift(latest_month, -1)
    prior_month = month_map.get(prior_month_key, {})
    previous_month = month_map.get(previous_month_key, {})

    checkpoints: list[dict[str, Any]] = []
    previous_semiconductor_yoy: float | None = None
    previous_total_yoy: float | None = None
    for stage in sorted(current_month):
        row = current_month[stage]
        prior_row = prior_month.get(stage)
        previous_month_row = previous_month.get(stage)
        total = _ten_day_metric_row(row, prior_row, previous_month_row, "itemUsdAmt00")
        semiconductor = _ten_day_metric_row(row, prior_row, previous_month_row, "itemUsdAmt01")
        total_amount = total.get("exportsUsdBillion")
        semi_amount = semiconductor.get("exportsUsdBillion")
        total_delta = total.get("deltaYoYUsdBillion")
        semi_delta = semiconductor.get("deltaYoYUsdBillion")
        checkpoint = {
            "stage": stage,
            "label": _ten_day_stage_label(stage),
            "periodRaw": str(row.get("priodDt") or "").strip(),
            "total": total,
            "semiconductor": semiconductor,
            "semiconductorSharePct": round(semi_amount / total_amount * 100.0, 1)
                if semi_amount is not None and total_amount and total_amount > 0 else None,
            "semiconductorContributionPct": round(semi_delta / total_delta * 100.0, 1)
                if semi_delta is not None and total_delta not in (None, 0) else None,
            "semiconductorYoYAccelerationPp": round(semiconductor["exportYoY"] - previous_semiconductor_yoy, 1)
                if semiconductor.get("exportYoY") is not None and previous_semiconductor_yoy is not None else None,
            "totalYoYAccelerationPp": round(total["exportYoY"] - previous_total_yoy, 1)
                if total.get("exportYoY") is not None and previous_total_yoy is not None else None,
        }
        checkpoints.append(checkpoint)
        if semiconductor.get("exportYoY") is not None:
            previous_semiconductor_yoy = semiconductor["exportYoY"]
        if total.get("exportYoY") is not None:
            previous_total_yoy = total["exportYoY"]

    latest_stage = max(current_month)
    latest_row = current_month[latest_stage]
    latest_prior = prior_month.get(latest_stage)
    latest_previous_month = previous_month.get(latest_stage)
    items: list[dict[str, Any]] = []
    for field, key, name in TEN_DAY_EXPORT_FIELDS[1:]:
        metric = _ten_day_metric_row(latest_row, latest_prior, latest_previous_month, field)
        if metric["exportsUsdBillion"] is None:
            continue
        items.append({
            "key": key,
            "name": name,
            **metric,
        })
    items.sort(key=lambda item: item.get("exportsUsdBillion") or 0.0, reverse=True)
    landing_projection = _build_landing_projection(month_map, latest_month)

    return {
        "schemaVersion": 2,
        "status": "official_preliminary_api",
        "period": _display_period(latest_month),
        "periodLabel": f"{latest_month[:4]}년 {int(latest_month[4:6])}월",
        "latestStage": latest_stage,
        "latestStageLabel": _ten_day_stage_label(latest_stage),
        "checkpoints": checkpoints,
        "items": items,
        "landingProjection": landing_projection,
        "meta": {
            "provider": "Korea Customs Service / data.go.kr",
            "basis": "수출신고수리일 기준 10일 단위 누적 잠정치",
            "unit": "USD billion (provider source: USD thousand)",
            "classification": "Korea Customs 10 major export product categories; not HS monthly classification",
            "queryRange": f"{_display_period(query_start)}~{_display_period(query_end)}",
            "landingModel": "rolling completion-ratio median with interquartile range and 24-month backtest",
            "cacheTtlSec": PROVISIONAL_CACHE_TTL_SEC,
        },
        "source": {
            "name": "관세청 수출 주요품목별 10일 단위 잠정치 통계",
            "url": "https://www.data.go.kr/data/15157908/openapi.do",
        },
    }


async def _refresh_provisional_radar() -> dict[str, Any]:
    async with _PROVISIONAL_CACHE_LOCK:
        age = time.time() - float(_PROVISIONAL_CACHE.get("timestamp") or 0.0)
        cached = _PROVISIONAL_CACHE.get("data")
        if cached is not None and age < PROVISIONAL_CACHE_TTL_SEC:
            return cached
        try:
            data = await asyncio.to_thread(_build_provisional_radar)
            _PROVISIONAL_CACHE["data"] = data
            _PROVISIONAL_CACHE["timestamp"] = time.time()
            _PROVISIONAL_CACHE["lastError"] = None
            return data
        except Exception as exc:
            _PROVISIONAL_CACHE["lastError"] = str(exc)
            raise


def _semiconductor_segment(key: str) -> dict[str, str] | None:
    return next((row for row in SEMICONDUCTOR_SEGMENTS if row["key"] == key), None)


def _fetch_semiconductor_country_pair(
    segment: dict[str, str],
    country: dict[str, str],
    period: str,
    prior: str,
) -> dict[str, Any] | None:
    current_rows = _request_rows(
        ITEM_COUNTRY_URL,
        strtYymm=period,
        endYymm=period,
        hsSgn=segment["code"],
        cntyCd=country["code"],
    )
    prior_rows = _request_rows(
        ITEM_COUNTRY_URL,
        strtYymm=prior,
        endYymm=prior,
        hsSgn=segment["code"],
        cntyCd=country["code"],
    )
    current = _country_export(current_rows, period)
    previous = _country_export(prior_rows, prior)
    if current is None:
        return None
    return {
        "name": country["name"],
        "code": country["code"],
        "exportsUsdBillion": _billion(current),
        "priorExportsUsdBillion": _billion(previous),
        "exportYoY": _pct(current, previous),
        "deltaUsdBillion": _billion(current - (previous or 0.0)) if previous is not None else None,
    }


def _build_semiconductor_country_matrix(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw_period = snapshot.get("itemPeriod")
    period = str(raw_period or "").replace("-", "")
    if not period:
        raise CustomsApiError("반도체 국가 분석 기준월이 없습니다.")
    prior = _month_shift(period, -12)
    breakdown = {
        row.get("key"): row
        for row in (snapshot.get("semiconductorBreakdown") or [])
        if row.get("key")
    }

    segments = [
        row for row in (
            _semiconductor_segment(key) for key in SEMICONDUCTOR_COUNTRY_SEGMENT_KEYS
        )
        if row
    ]
    results: dict[str, list[dict[str, Any]]] = {row["key"]: [] for row in segments}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="customs-semi-country") as pool:
        future_map = {
            pool.submit(
                _fetch_semiconductor_country_pair,
                segment,
                country,
                period,
                prior,
            ): (segment, country)
            for segment in segments
            for country in SEMICONDUCTOR_COUNTRY_MARKETS
        }
        for future in as_completed(future_map):
            segment, country = future_map[future]
            try:
                row = future.result()
                if row:
                    results[segment["key"]].append(row)
            except Exception as exc:
                errors.append(f"{segment['name']}·{country['name']}: {exc}")

    segment_rows: list[dict[str, Any]] = []
    market_order = {row["code"]: index for index, row in enumerate(SEMICONDUCTOR_COUNTRY_MARKETS)}
    for segment in segments:
        countries = results.get(segment["key"], [])
        countries.sort(key=lambda row: market_order.get(row["code"], 999))
        total = _number((breakdown.get(segment["key"]) or {}).get("exportsUsdBillion"))
        covered = sum((row.get("exportsUsdBillion") or 0.0) for row in countries)
        for row in countries:
            row["sharePct"] = round((row["exportsUsdBillion"] or 0.0) / total * 100.0, 1) if total and total > 0 else None

        comparable = [row for row in countries if row.get("deltaUsdBillion") is not None]
        leader = max(countries, key=lambda row: row.get("exportsUsdBillion") or 0.0, default=None)
        growth = max(comparable, key=lambda row: row.get("deltaUsdBillion") or 0.0, default=None)
        decline = min(comparable, key=lambda row: row.get("deltaUsdBillion") or 0.0, default=None)
        segment_rows.append({
            "key": segment["key"],
            "name": segment["name"],
            "code": segment["code"],
            "period": _display_period(period),
            "exportsUsdBillion": total,
            "coveredSharePct": round(covered / total * 100.0, 1) if total and total > 0 else None,
            "leaderCountry": leader.get("name") if leader else None,
            "growthLeaderCountry": growth.get("name") if growth and (growth.get("deltaUsdBillion") or 0) > 0 else None,
            "declineLeaderCountry": decline.get("name") if decline and (decline.get("deltaUsdBillion") or 0) < 0 else None,
            "countries": countries,
        })

    return {
        "schemaVersion": 1,
        "period": _display_period(period),
        "segments": segment_rows,
        "markets": [dict(row) for row in SEMICONDUCTOR_COUNTRY_MARKETS],
        "meta": {
            "provider": "Korea Customs Service / data.go.kr",
            "scope": "CN, HK, VN, TW, US, JP configured semiconductor markets; not a global ranking",
            "comparison": "current month vs same month one year earlier",
            "cacheTtlSec": SEMICONDUCTOR_COUNTRY_CACHE_TTL_SEC,
            "errors": errors[:8],
        },
    }


async def _refresh_semiconductor_country_matrix() -> dict[str, Any]:
    async with _SEMICONDUCTOR_COUNTRY_LOCK:
        age = time.time() - float(_SEMICONDUCTOR_COUNTRY_CACHE.get("timestamp") or 0.0)
        cached = _SEMICONDUCTOR_COUNTRY_CACHE.get("data")
        if cached is not None and age < SEMICONDUCTOR_COUNTRY_CACHE_TTL_SEC:
            return cached

        snapshot = _CACHE.get("data")
        if snapshot is None:
            snapshot = await _refresh_cache()

        try:
            data = await asyncio.to_thread(_build_semiconductor_country_matrix, snapshot)
            _SEMICONDUCTOR_COUNTRY_CACHE["data"] = data
            _SEMICONDUCTOR_COUNTRY_CACHE["timestamp"] = time.time()
            _SEMICONDUCTOR_COUNTRY_CACHE["lastError"] = None
            return data
        except Exception as exc:
            _SEMICONDUCTOR_COUNTRY_CACHE["lastError"] = str(exc)
            raise


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
    momentum = _build_momentum_summary(history)
    semiconductor_breakdown = (
        copy.deepcopy((snapshot or {}).get("semiconductorBreakdown") or [])
        if key == "semiconductor" else []
    )

    return {
        "schemaVersion": 2,
        "key": group["key"],
        "name": group["name"],
        "note": group["note"],
        "period": _display_period(period),
        "history": history,
        "momentum": momentum,
        "semiconductorBreakdown": semiconductor_breakdown,
        "countries": countries,
        "meta": {
            "provider": "Korea Customs Service / data.go.kr",
            "countryScope": "US, CN, VN, JP, TW configured major markets; not a global top-country ranking",
            "unitValueMethod": "export 신고미화금액 / 순중량(kg)",
            "semiconductorClassification": (
                "2026 HSK: DRAM 8542321010, SRAM 8542321020, Flash memory 8542321030, "
                "memory MCP 8542323000, DRAM module 8473304060; "
                "HBM is not separately identifiable from the Customs HS statistics"
                if key == "semiconductor" else None
            ),
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
    breadth: dict[str, Any] | None = None
    semiconductor_breakdown: list[dict[str, Any]] = []
    try:
        item_period = _find_item_period_candidate(latest)
        if item_period:
            # Once a lightweight probe identifies the latest available detail
            # month, fetch current/prior-year full tables in parallel. MoM uses
            # only five targeted HSK requests.
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="customs-item-build") as pool:
                current_future = pool.submit(_fetch_item_rows, item_period)
                prior_future = pool.submit(_fetch_item_rows, _month_shift(item_period, -12))
                previous_month_future = pool.submit(
                    _fetch_semiconductor_previous_month_rows,
                    _month_shift(item_period, -1),
                )
                item_rows = current_future.result()
                prior_item_rows = prior_future.result()
                previous_month_item_rows = previous_month_future.result()
            items = _build_items_from_rows(item_rows, prior_item_rows, item_period)
            breadth = _build_hs2_breadth(item_rows, prior_item_rows, item_period)
            semiconductor_breakdown = _build_semiconductor_breakdown_from_rows(
                item_rows,
                prior_item_rows,
                previous_month_item_rows,
                item_period,
            )
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
        "schemaVersion": 6,
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
        "semiconductorBreakdown": semiconductor_breakdown,
        "breadth": breadth,
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
            "itemMethod": "lightweight HSK availability probe + parallel current/prior full tables; targeted previous-month semiconductor HSK queries",
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


@router.get("/api/export-momentum/provisional")
async def export_momentum_provisional(response: Response):
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    cached = _PROVISIONAL_CACHE.get("data")
    age = time.time() - float(_PROVISIONAL_CACHE.get("timestamp") or 0.0)
    if cached is not None and age < PROVISIONAL_CACHE_TTL_SEC:
        result = copy.deepcopy(cached)
        result.setdefault("meta", {})["cacheStatus"] = "fresh"
        return result
    try:
        data = await _refresh_provisional_radar()
        result = copy.deepcopy(data)
        result.setdefault("meta", {})["cacheStatus"] = "fresh"
        return result
    except Exception as exc:
        if cached:
            result = copy.deepcopy(cached)
            result.setdefault("meta", {})["cacheStatus"] = "stale-error"
            result["meta"]["lastRefreshError"] = str(exc)[:240]
            return result
        raise HTTPException(
            status_code=503,
            detail={"code": "EXPORT_PROVISIONAL_UNAVAILABLE", "message": str(exc)[:300]},
        ) from exc


@router.get("/api/export-momentum/semiconductor-countries")
async def export_momentum_semiconductor_countries(response: Response):
    response.headers["Cache-Control"] = "public, max-age=900, stale-while-revalidate=43200"
    cached = _SEMICONDUCTOR_COUNTRY_CACHE.get("data")
    age = time.time() - float(_SEMICONDUCTOR_COUNTRY_CACHE.get("timestamp") or 0.0)
    if cached is not None and age < SEMICONDUCTOR_COUNTRY_CACHE_TTL_SEC:
        result = copy.deepcopy(cached)
        result.setdefault("meta", {})["cacheStatus"] = "fresh"
        return result
    try:
        data = await _refresh_semiconductor_country_matrix()
        result = copy.deepcopy(data)
        result.setdefault("meta", {})["cacheStatus"] = "fresh"
        return result
    except Exception as exc:
        if cached:
            result = copy.deepcopy(cached)
            result.setdefault("meta", {})["cacheStatus"] = "stale-error"
            result["meta"]["lastRefreshError"] = str(exc)[:240]
            return result
        raise HTTPException(
            status_code=503,
            detail={"code": "SEMICONDUCTOR_COUNTRY_UNAVAILABLE", "message": str(exc)[:300]},
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
