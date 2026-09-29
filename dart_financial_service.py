"""Conservative, report-based revenue and operating-profit history from OpenDART."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import threading
import time

from fastapi import APIRouter, HTTPException, Query
import requests

from dart_business_service import OPEN_DART_BASE, HEADERS, _corp_codes, _redis_client, _stock_code

router = APIRouter()
KST = timezone(timedelta(hours=9))
CACHE_TTL = 24 * 3600
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_REFRESHING: set[str] = set()
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dart-financial")
STATIC_PATH = os.path.join("static", "data", "dart_financial_history.json")
_STATIC: tuple[float, dict] = (0.0, {})


def _amount(value):
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").strip()
        if text.startswith("△"):
            text = "-" + text[1:].strip()
        elif text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1].strip()
        return int(text)
    except (TypeError, ValueError):
        return None


def _pick_account(rows, names, ids):
    """Use a single primary income-statement row, never sum ambiguous rows."""
    candidates = [r for r in rows if r.get("sj_div") in {"IS", "CIS"}
                  and str(r.get("account_detail") or "-").strip() in {"", "-"}
                  and (r.get("account_id") in ids or str(r.get("account_nm") or "").replace(" ", "") in names)]
    for statement in ("IS", "CIS"):
        subset = [r for r in candidates if r.get("sj_div") == statement]
        for account_id in ids:
            standard = [r for r in subset if r.get("account_id") == account_id]
            if len(standard) == 1:
                return standard[0]
            if standard:
                return None
        if len(subset) == 1:
            return subset[0]
        if subset:
            return None
    return None


REVENUE_NAMES = {"매출액", "매출", "영업수익", "수익(매출액)", "수익"}
REVENUE_IDS = ("ifrs-full_Revenue", "ifrs_Revenue", "ifrs-full_RevenueFromContractsWithCustomers")
OPERATING_NAMES = {"영업이익", "영업이익(손실)", "영업손익"}
OPERATING_IDS = ("dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities")


def parse_financial_statement(rows, year, report_code):
    revenue = _pick_account(rows, REVENUE_NAMES, REVENUE_IDS)
    operating = _pick_account(rows, OPERATING_NAMES, OPERATING_IDS)
    if not revenue or not operating:
        return None
    currency = str(revenue.get("currency") or "KRW").strip()
    if currency != str(operating.get("currency") or currency).strip():
        return None
    rcept_no = str(revenue.get("rcept_no") or "")
    if rcept_no != str(operating.get("rcept_no") or "") or len(rcept_no) != 14:
        return None
    if report_code == "11011":
        periods = []
        for offset, key in ((2, "bfefrmtrm_amount"), (1, "frmtrm_amount"), (0, "thstrm_amount")):
            sales = _amount(revenue.get(key))
            profit = _amount(operating.get(key))
            if sales is not None and profit is not None:
                periods.append({"year": year - offset, "revenue": sales, "operatingProfit": profit})
        if not periods:
            return None
        return {"currency": currency, "rceptNo": rcept_no, "years": periods}
    current_sales = _amount(revenue.get("thstrm_add_amount"))
    current_profit = _amount(operating.get("thstrm_add_amount"))
    prior_sales = _amount(revenue.get("frmtrm_add_amount"))
    prior_profit = _amount(operating.get("frmtrm_add_amount"))
    if current_sales is None or current_profit is None:
        return None
    quarter = {"11013": 1, "11012": 2, "11014": 3}.get(report_code)
    if not quarter:
        return None
    return {"currency": currency, "rceptNo": rcept_no, "year": year, "quarter": quarter,
            "revenue": current_sales, "operatingProfit": current_profit,
            "priorRevenue": prior_sales, "priorOperatingProfit": prior_profit}


def _get_statement(api_key, corp_code, year, report_code, fs_div="CFS"):
    response = requests.get(f"{OPEN_DART_BASE}/fnlttSinglAcntAll.json", params={
        "crtfc_key": api_key, "corp_code": corp_code, "bsns_year": year,
        "reprt_code": report_code, "fs_div": fs_div,
    }, headers=HEADERS, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "000":
        return None
    return parse_financial_statement(payload.get("list") or [], year, report_code)


def _persistent(code):
    try:
        client = _redis_client()
        raw = client.get(f"chartview:dart-financial:v1:{code}") if client else None
        value = json.loads(raw) if raw else None
        if isinstance(value, dict) and value.get("stockCode") == code:
            return value
    except Exception as exc:
        print(f"[DART financial] cache read failed: {type(exc).__name__}")
    return None


def _static_row(code):
    global _STATIC
    try:
        mtime = os.path.getmtime(STATIC_PATH)
    except OSError:
        return None
    with _LOCK:
        if _STATIC[0] != mtime:
            try:
                with open(STATIC_PATH, encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError):
                return None
            _STATIC = (mtime, payload)
        row = (_STATIC[1].get("companies") or {}).get(code)
    if (isinstance(row, dict) and row.get("available") is True
            and row.get("stockCode") == code and row.get("source") == "OpenDART"):
        return dict(row)
    return None


def _freshness(row):
    if not row:
        return (-1, -1, -1, "", "")
    interim = row.get("interim") or {}
    return (int(row.get("annualReportYear") or 0), int(interim.get("year") or 0),
            int(interim.get("quarter") or 0),
            str(row.get("annualSourceUrl") or "").split("rcpNo=")[-1],
            str(row.get("interimSourceUrl") or "").split("rcpNo=")[-1])


def _save(code, row):
    try:
        client = _redis_client()
        if client:
            client.set(f"chartview:dart-financial:v1:{code}", json.dumps(row, ensure_ascii=False))
    except Exception as exc:
        print(f"[DART financial] cache write failed: {type(exc).__name__}")


def _collect(code, ticker):
    now = datetime.now(KST)
    result = {"ticker": ticker, "stockCode": code, "available": False,
              "source": "OpenDART", "checkedAt": now.isoformat(timespec="seconds")}
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        result["reason"] = "api_key_unavailable"
        return result
    company = _corp_codes(key).get(code)
    if not company or not company.get("corpCode"):
        result["reason"] = "corp_code_unavailable"
        return result
    corp_code = company["corpCode"]
    def safe_statement(year, report_code, basis):
        try:
            return _get_statement(key, corp_code, year, report_code, basis)
        except requests.RequestException:
            return None

    codes = (["11014", "11012", "11013"] if now.month >= 11 else
             ["11012", "11013"] if now.month >= 8 else
             ["11013"] if now.month >= 5 else [])
    # The current interim filing and latest annual filing are independent DART
    # requests. Fetching them together halves the normal cold-lookup wait.
    with ThreadPoolExecutor(max_workers=2) as pool:
        annual_task = pool.submit(safe_statement, now.year - 1, "11011", "CFS")
        interim_task = pool.submit(safe_statement, now.year, codes[0], "CFS") if codes else None
        annual = annual_task.result()
        interim = interim_task.result() if interim_task else None
    year = now.year - 1
    fs_div = "CFS"
    if not annual:
        for candidate_year, candidate_basis in ((now.year - 1, "OFS"),
                                                  (now.year - 2, "CFS"),
                                                  (now.year - 2, "OFS")):
            annual = safe_statement(candidate_year, "11011", candidate_basis)
            if annual:
                year, fs_div = candidate_year, candidate_basis
                break
    if annual:
        result.update({"available": True, "basis": "연결재무제표" if fs_div == "CFS" else "별도재무제표", "currency": annual["currency"],
                       "annual": annual["years"], "annualReportYear": year,
                       "annualSourceUrl": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={annual['rceptNo']}"})
    # Only published periods can be requested; a later filing may still be unavailable.
    if annual and fs_div != "CFS":
        interim = None  # The parallel CFS value must not be mixed with OFS annuals.
    if not interim:
        for index, report_code in enumerate(codes):
            for candidate in ((fs_div,) if annual else ("CFS", "OFS")):
                if index == 0 and candidate == "CFS" and fs_div == "CFS":
                    continue  # Already attempted in parallel.
                interim = safe_statement(now.year, report_code, candidate)
                if interim:
                    fs_div = candidate
                    break
            if interim:
                break
    if interim and (not annual or interim["currency"] == annual["currency"]):
        result.update({"available": True, "basis": "연결재무제표" if fs_div == "CFS" else "별도재무제표", "currency": interim["currency"],
                       "interim": {k: v for k, v in interim.items() if k not in {"currency", "rceptNo"}},
                       "interimSourceUrl": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={interim['rceptNo']}"})
    if not result["available"]:
        result["reason"] = "consolidated_statement_unavailable"
    return result


def _refresh(code, ticker):
    try:
        row = _collect(code, ticker)
        with _LOCK:
            old = _CACHE.get(code)
            if row["available"] or not old or not old[1].get("available"):
                _CACHE[code] = (time.time(), row)
                if row["available"]:
                    _save(code, row)
            else:
                _CACHE[code] = (time.time(), old[1])
    except Exception as exc:
        print(f"[DART financial] refresh failed for {code}: {type(exc).__name__}: {exc}")
    finally:
        with _LOCK:
            _REFRESHING.discard(code)


def fetch_financial_history(ticker):
    code = _stock_code(ticker)
    with _LOCK:
        cached = _CACHE.get(code)
    if not cached:
        persisted = _persistent(code)
        static = _static_row(code)
        # At the same receipt, the newly validated checked-in row wins over a
        # Redis entry from an older parser revision.
        row = max((r for r in (static, persisted) if r and r.get("available")),
                  key=_freshness, default=None)
        if row:
            cached = (0, row)
            with _LOCK:
                _CACHE[code] = cached
    if cached:
        if time.time() - cached[0] >= CACHE_TTL:
            with _LOCK:
                if code not in _REFRESHING:
                    _REFRESHING.add(code)
                    _POOL.submit(_refresh, code, ticker)
        return dict(cached[1], ticker=ticker)
    row = _collect(code, ticker)
    with _LOCK:
        _CACHE[code] = (time.time(), row)
    if row["available"]:
        _save(code, row)
    return row


@router.get("/api/financial-history")
async def financial_history(ticker: str = Query(..., min_length=6, max_length=12)):
    try:
        _stock_code(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(fetch_financial_history, ticker)
