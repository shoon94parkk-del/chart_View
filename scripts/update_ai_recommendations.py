"""Build the daily, transparent TOP3 ledger and update its return track record.

The source screener is technical-only. Every displayed reason is calculated from
the published snapshot; the script does not invent fundamental research. A
secondary-price verification delay marks a pick provisional but does not block a
fresh, market-wide screener publication.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "static" / "data"
REC_PATH = DATA_DIR / "ai_recommendations.json"
RANKING_PATH = DATA_DIR / "ai_daily_rankings.json"
RANKING_META_PATH = DATA_DIR / "ai_daily_rankings_meta.json"
SCREENER_PATH = DATA_DIR / "screener.json"
TOP100_PATH = DATA_DIR / "screener_top100.json"


def load_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError, TypeError):
        return default


def number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(now: float, base: float) -> float | None:
    return round((now / base - 1.0) * 100.0, 2) if base else None


def technical_total(row: dict) -> int:
    """A reproducible 100-point ordering score from the technical snapshot."""
    base = min(30.0, max(0.0, number(row.get("technicalScore"))))
    trend = (8 if row.get("aligned") else 0) + (5 if row.get("above60") else 0) + (4 if row.get("above20") else 0) + (3 if row.get("cross20") else 0)
    volume_ratio = number(row.get("volumeRatio"))
    volume = 0 if volume_ratio < 1 else min(15, round((volume_ratio - 1) * 10))
    ret5, ret20 = number(row.get("ret5")), number(row.get("ret20"))
    momentum = min(8, max(0, round(ret5 / 2))) + min(7, max(0, round(ret20 / 5)))
    penalty = min(15, max(0, round(number((row.get("technicalBreakdown") or {}).get("chasePenalty")))))
    return max(0, min(100, int(round(base * 2 + trend + volume + momentum - penalty))))


def reason_for(row: dict) -> str:
    parts = [f"기술 점수 {int(number(row.get('technicalScore')))}/30"]
    if row.get("aligned"):
        parts.append("주가와 20·60·120일선 정배열")
    elif row.get("above60"):
        parts.append("20일선·60일선 위")
    elif row.get("above20"):
        parts.append("20일선 위")
    if row.get("cross20"):
        parts.append("20일선 상향 돌파")
    ratio = number(row.get("volumeRatio"))
    if ratio >= 1.2:
        parts.append(f"거래량 {ratio:.2f}배")
    ret5 = number(row.get("ret5"))
    if ret5:
        parts.append(f"5일 수익률 {ret5:+.2f}%")
    return " · ".join(parts) + "."


def grade_for(row: dict) -> str:
    return "가격 2차 검증 완료" if (row.get("priceValidation") or {}).get("status") == "verified" else "가격 2차 검증 대기"


def build_day(top100: dict) -> dict:
    trade_date = str(top100.get("tradeDate") or "")
    verification = top100.get("verification") or {}
    candidates = [row for row in (top100.get("stocks") or []) if (row.get("priceValidation") or {}).get("status") != "mismatch"]
    if not trade_date or len(candidates) < 3:
        raise RuntimeError("not enough non-mismatched exact-date candidates for daily TOP3")
    ordered = sorted(candidates, key=lambda row: (technical_total(row), number(row.get("technicalScore")), number(row.get("avgValue20"))), reverse=True)[:3]
    top3 = [{
        "rank": rank, "code": str(row.get("code") or ""), "symbol": str(row.get("symbol") or "").upper(),
        "name": row.get("name") or row.get("symbol") or "-", "close": number(row.get("price")),
        "previousClose": number(row.get("previousClose")), "changePct": round(number(row.get("change1d")), 2),
        "totalScore": technical_total(row), "technicalScore": int(number(row.get("technicalScore"))),
        "grade": grade_for(row), "reason": reason_for(row),
    } for rank, row in enumerate(ordered, start=1)]
    mismatches, pending = int(verification.get("priceMismatchCount") or 0), int(verification.get("pricePendingCount") or 0)
    if mismatches:
        status = f"잠정 TOP3 — {trade_date} 종가 기준, 보조 가격소스 불일치 {mismatches}건은 후보에서 제외"
    elif pending:
        status = f"잠정 TOP3 — {trade_date} 종가 기준, 보조 가격소스 확인 대기 {pending}건"
    else:
        status = f"TOP3 — {trade_date} 종가 2차 가격 검증 완료"
    return {"tradeDate": trade_date, "status": status, "top3": top3, "verification": verification}


def refresh_records(days: list[dict], screener: dict, existing: list[dict]) -> list[dict]:
    prices = {str(row.get("symbol") or "").upper(): number(row.get("price") or row.get("close")) for row in (screener.get("stocks") or [])}
    previous = {(str(row.get("recommendedDate") or ""), str(row.get("symbol") or "").upper(), int(number(row.get("rank")))): row for row in existing}
    records = []
    for day in sorted(days, key=lambda row: str(row.get("tradeDate") or "")):
        date = str(day.get("tradeDate") or "")
        for pick in (day.get("top3") or [])[:3]:
            symbol, rank, entry = str(pick.get("symbol") or "").upper(), int(number(pick.get("rank"))), number(pick.get("close"))
            old = previous.get((date, symbol, rank), {})
            current = prices.get(symbol) or entry
            current_return = pct(current, entry)
            best = max(number(old.get("bestReturnPct"), current_return or 0), current_return or 0)
            records.append({
                "recommendedDate": date, "rank": rank, "symbol": symbol, "code": pick.get("code") or "", "name": pick.get("name") or symbol,
                "recommendedPrice": entry, "currentPrice": current, "returnPct": current_return, "bestReturnPct": round(best, 2),
                "lastUpdatedTradeDate": screener.get("tradeDate") or screener.get("date"), "status": "tracking", "statusLabel": "성과 추적 중",
                "grade": pick.get("grade") or "관찰", "reason": pick.get("reason") or "", "score": pick.get("totalScore"),
            })
    return records


def main() -> None:
    now = datetime.now(KST).isoformat(timespec="seconds")
    rankings = load_json(RANKING_PATH, {"days": []})
    recommendations = load_json(REC_PATH, {"recommendations": []})
    screener, top100 = load_json(SCREENER_PATH, {}), load_json(TOP100_PATH, {})
    day = build_day(top100)
    days = [row for row in (rankings.get("days") or []) if str(row.get("tradeDate") or "") != day["tradeDate"]] + [day]
    days.sort(key=lambda row: str(row.get("tradeDate") or ""))
    records = refresh_records(days, screener, recommendations.get("recommendations") or [])
    RANKING_PATH.write_text(json.dumps({"updated": now, "days": days}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REC_PATH.write_text(json.dumps({"updated": now, "recommendations": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RANKING_META_PATH.write_text(json.dumps({"updated": now, "tradeDate": day["tradeDate"], "daysCount": len(days)}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved daily TOP3 for {day['tradeDate']} and {len(records)} track-record rows")


if __name__ == "__main__":
    main()
