from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "static" / "data"
SRC = DATA / "screener.json"
META = DATA / "screener_meta.json"
OUT = DATA / "screener_top100.json"
VERIFY_OUT = DATA / "screener_validation.json"
RANKINGS = DATA / "ai_daily_rankings.json"
RECOMMENDATIONS = DATA / "ai_recommendations.json"
CONSENSUS = DATA / "consensus_cache.json"
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 ChartView/ScreenerVerify",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://m.stock.naver.com/",
}
TECHNICAL_POOL_SIZE = 100
GROWTH_POOL_SIZE = 40
CARRYOVER_DAYS = 10


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


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


def _growth_score(quote: dict) -> float:
    """Candidate-discovery score only. Final recommendation still uses the 70+30 model."""
    periods = quote.get("periods") or {}
    score = 0.0
    for key, weight in (("0y", 1.0), ("+1y", 1.25), ("0q", 0.45), ("+1q", 0.65)):
        p = periods.get(key) or {}
        earnings = p.get("earnings") or {}
        revenue = p.get("revenue") or {}
        eps_growth = _number(earnings.get("growth"))
        rev_growth = _number(revenue.get("growth"))
        if eps_growth is not None:
            score += max(-1.0, min(eps_growth, 3.0)) * 12.0 * weight
        if rev_growth is not None:
            score += max(-0.5, min(rev_growth, 2.0)) * 8.0 * weight
        trend = p.get("epsTrend") or {}
        current = _number(trend.get("current"))
        ago30 = _number(trend.get("30daysAgo"))
        if current is not None and ago30 not in (None, 0):
            revision = (current / ago30 - 1.0)
            score += max(-0.5, min(revision, 0.5)) * 20.0 * weight
    return round(score, 3)


def _verify_with_naver(stock: dict, trade_date: str) -> dict:
    code = stock.get("code")
    source_close = _number(stock.get("price"))
    source_prev = _number(stock.get("previousClose"))
    source_change = _number(stock.get("change1d"))
    result = {"provider": "Naver Finance KRX/Koscom", "status": "pending", "asOf": None,
              "close": None, "changePct": None, "reason": None}
    try:
        response = requests.get(f"https://m.stock.naver.com/api/stock/{code}/basic", headers=HEADERS, timeout=(2.5, 5.0))
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
        if naver_close is None or source_close is None:
            result["reason"] = "missing close price"
            return result
        close_match = abs(naver_close - source_close) < 0.5
        calc_change = round((source_close / source_prev - 1) * 100, 2) if source_prev and source_prev > 0 else None
        arithmetic_match = calc_change is not None and source_change is not None and abs(calc_change - source_change) <= 0.02
        change_match = naver_change is None or source_change is None or abs(naver_change - source_change) <= 0.05
        if close_match and arithmetic_match and change_match:
            result["status"] = "verified"
            result["reason"] = "date/close/change arithmetic matched"
        else:
            result["status"] = "mismatch"
            result["reason"] = f"close_match={close_match}, arithmetic_match={arithmetic_match}, change_match={change_match}"
    except Exception as exc:
        result["reason"] = f"secondary source unavailable: {type(exc).__name__}"
    return result


def main():
    payload = _load(SRC, {})
    meta = _load(META, {})
    trade_date = str(payload.get("tradeDate") or "")
    stocks = payload.get("stocks") or []
    if not trade_date or len(stocks) < 100:
        raise RuntimeError(f"invalid screener snapshot: tradeDate={trade_date!r}, stocks={len(stocks)}")
    if str(meta.get("tradeDate") or "") != trade_date:
        raise RuntimeError(f"meta tradeDate mismatch: meta={meta.get('tradeDate')} screener={trade_date}")
    if int(meta.get("count") or 0) != len(stocks):
        raise RuntimeError(f"meta count mismatch: meta={meta.get('count')} screener={len(stocks)}")

    same_day = [row for row in stocks if str(row.get("date") or "") == trade_date]
    if len(same_day) < 100:
        raise RuntimeError(f"insufficient exact-date universe: tradeDate={trade_date}, exactDateStocks={len(same_day)}")
    by_symbol = {str(row.get("symbol")): row for row in same_day if row.get("symbol")}

    selected: dict[str, dict] = {}
    sources: dict[str, set[str]] = {}
    def add(symbol: str, source: str):
        row = by_symbol.get(symbol)
        if not row:
            return
        if symbol not in selected:
            selected[symbol] = dict(row)
            sources[symbol] = set()
        sources[symbol].add(source)

    # 1) Daily technical discovery. This is no longer an exclusion gate.
    for row in same_day[:TECHNICAL_POOL_SIZE]:
        add(str(row.get("symbol")), "technical_top100")

    # 2) Carry forward recent TOP10/TOP3 so a strong company cannot disappear because of one weak chart day.
    rankings = _load(RANKINGS, {})
    days = rankings.get("days") or []
    for day in days[-CARRYOVER_DAYS:]:
        for row in (day.get("top10") or []) + (day.get("top3") or []):
            symbol = str(row.get("symbol") or "")
            if symbol:
                add(symbol, "recent_ai_rank")

    # 3) Carry active/tracking recommendations.
    recs = _load(RECOMMENDATIONS, {})
    for row in recs.get("recommendations") or []:
        if str(row.get("status") or "").lower() in {"active", "tracking"}:
            symbol = str(row.get("symbol") or "")
            if symbol:
                add(symbol, "active_recommendation")

    # 4) Add estimate-growth candidates independently of chart rank.
    consensus = _load(CONSENSUS, {})
    growth_ranked = []
    for symbol, quote in (consensus.get("quotes") or {}).items():
        if symbol in by_symbol:
            growth_ranked.append((_growth_score(quote), symbol))
    growth_ranked.sort(reverse=True)
    for growth_score, symbol in growth_ranked[:GROWTH_POOL_SIZE]:
        add(symbol, "consensus_growth")
        selected[symbol]["growthDiscoveryScore"] = growth_score

    candidates = list(selected.values())
    for row in candidates:
        symbol = str(row.get("symbol"))
        row["candidateSources"] = sorted(sources.get(symbol) or [])

    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {pool.submit(_verify_with_naver, row, trade_date): idx for idx, row in enumerate(candidates)}
        for future in as_completed(future_map):
            candidates[future_map[future]]["priceValidation"] = future.result()

    verified = sum(1 for r in candidates if r["priceValidation"]["status"] == "verified")
    pending = sum(1 for r in candidates if r["priceValidation"]["status"] == "pending")
    mismatch = sum(1 for r in candidates if r["priceValidation"]["status"] == "mismatch")
    verification = {
        "tradeDate": trade_date,
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "sourceUniverseCount": len(stocks),
        "exactDateUniverseCount": len(same_day),
        "candidateCount": len(candidates),
        "technicalDiscoveryCount": TECHNICAL_POOL_SIZE,
        "growthDiscoveryLimit": GROWTH_POOL_SIZE,
        "carryoverDays": CARRYOVER_DAYS,
        "secondaryProvider": "Naver Finance KRX/Koscom",
        "priceVerifiedCount": verified,
        "pricePendingCount": pending,
        "priceMismatchCount": mismatch,
        "aiInputReady": True,
        "policy": (
            "Candidate pool = technical top100 + recent AI ranks + active recommendations + consensus-growth candidates. "
            "Technical score is discovery/timing only and must never be an exclusion gate for a fundamentally strong company. "
            "Final ranking remains fundamentals/industry 70 + technical 30. Price mismatch is a validation flag for final picks, "
            "not a reason to delete the company from the research pool."
        ),
    }
    out = {k: payload.get(k) for k in ("updated", "tradeDate", "count", "universeCount", "scoreModel", "source")}
    out["candidateModel"] = "technical discovery + growth discovery + recent-rank carryover"
    out["verification"] = verification
    out["stocks"] = candidates
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    VERIFY_OUT.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(candidates)} blended candidates -> {OUT}; verified={verified}, pending={pending}, mismatch={mismatch}")


if __name__ == "__main__":
    main()
