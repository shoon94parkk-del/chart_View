from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "static" / "data" / "screener.json"
META = ROOT / "static" / "data" / "screener_meta.json"
OUT = ROOT / "static" / "data" / "screener_top100.json"
VERIFY_OUT = ROOT / "static" / "data" / "screener_validation.json"
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 ChartView/ScreenerVerify",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://m.stock.naver.com/",
}


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _trade_date(value: str | None) -> str | None:
    value = str(value or "").strip()
    return value[:10] if len(value) >= 10 else None


def _verify_with_naver(stock: dict, trade_date: str) -> dict:
    code = stock.get("code")
    yahoo_close = _number(stock.get("price"))
    yahoo_prev = _number(stock.get("previousClose"))
    yahoo_change = _number(stock.get("change1d"))
    result = {
        "provider": "Naver Finance KRX/Koscom",
        "status": "pending",
        "asOf": None,
        "close": None,
        "changePct": None,
        "reason": None,
    }
    try:
        response = requests.get(
            f"https://m.stock.naver.com/api/stock/{code}/basic",
            headers=HEADERS,
            timeout=(2.5, 5.0),
        )
        response.raise_for_status()
        data = response.json()
        naver_close = _number(data.get("closePrice"))
        naver_change = _number(data.get("fluctuationsRatio"))
        as_of = str(data.get("localTradedAt") or "").strip() or None
        naver_date = _trade_date(as_of)
        result.update({"asOf": as_of, "close": naver_close, "changePct": naver_change})

        if naver_date != trade_date:
            result["reason"] = f"secondary source date {naver_date or 'unknown'} != {trade_date}"
            return result
        if naver_close is None or yahoo_close is None:
            result["reason"] = "missing close price"
            return result

        close_match = abs(naver_close - yahoo_close) < 0.5
        calc_change = None
        if yahoo_prev and yahoo_prev > 0:
            calc_change = round((yahoo_close / yahoo_prev - 1) * 100, 2)
        arithmetic_match = calc_change is not None and yahoo_change is not None and abs(calc_change - yahoo_change) <= 0.02
        change_match = naver_change is None or yahoo_change is None or abs(naver_change - yahoo_change) <= 0.05

        if close_match and arithmetic_match and change_match:
            result["status"] = "verified"
            result["reason"] = "date/close/change arithmetic matched"
        else:
            result["status"] = "mismatch"
            result["reason"] = (
                f"close_match={close_match}, arithmetic_match={arithmetic_match}, change_match={change_match}"
            )
    except Exception as exc:
        result["reason"] = f"secondary source unavailable: {type(exc).__name__}"
    return result


def main():
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    trade_date = str(payload.get("tradeDate") or "")
    stocks = payload.get("stocks") or []

    # Never silently treat a truncated/empty large file as a valid screener snapshot.
    if not trade_date or len(stocks) < 100:
        raise RuntimeError(f"invalid screener snapshot: tradeDate={trade_date!r}, stocks={len(stocks)}")
    if str(meta.get("tradeDate") or "") != trade_date:
        raise RuntimeError(f"meta tradeDate mismatch: meta={meta.get('tradeDate')} screener={trade_date}")
    if int(meta.get("count") or 0) != len(stocks):
        raise RuntimeError(f"meta count mismatch: meta={meta.get('count')} screener={len(stocks)}")

    candidates = [dict(row) for row in stocks[:100]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {pool.submit(_verify_with_naver, row, trade_date): idx for idx, row in enumerate(candidates)}
        for future in as_completed(future_map):
            idx = future_map[future]
            candidates[idx]["priceValidation"] = future.result()

    verified = sum(1 for row in candidates if row["priceValidation"]["status"] == "verified")
    pending = sum(1 for row in candidates if row["priceValidation"]["status"] == "pending")
    mismatch = sum(1 for row in candidates if row["priceValidation"]["status"] == "mismatch")
    exact_date = sum(1 for row in candidates if str(row.get("date") or "") == trade_date)

    verification = {
        "tradeDate": trade_date,
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "candidateCount": len(candidates),
        "candidateExactDateCount": exact_date,
        "secondaryProvider": "Naver Finance KRX/Koscom",
        "priceVerifiedCount": verified,
        "pricePendingCount": pending,
        "priceMismatchCount": mismatch,
        "aiInputReady": exact_date == len(candidates) and mismatch == 0,
        "policy": (
            "AI should read screener_top100.json first. pending means the second source is not updated yet; "
            "mismatch blocks A/TOP3 until resolved. Never infer that screener.json is empty from a large-file fetch failure."
        ),
    }

    out = {k: payload.get(k) for k in ("updated", "tradeDate", "count", "universeCount", "scoreModel", "source")}
    out["verification"] = verification
    out["stocks"] = candidates
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    VERIFY_OUT.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Saved {len(candidates)} candidates -> {OUT}; "
        f"verified={verified}, pending={pending}, mismatch={mismatch}, exactDate={exact_date}"
    )


if __name__ == "__main__":
    main()
