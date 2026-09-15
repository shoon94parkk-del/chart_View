"""Refresh returns for GPT-reviewed daily TOP3 records.

This intentionally does *not* select stocks. The scheduled screener only
publishes a candidate universe. A separately scheduled GPT review commits a
completed ``gpt_screener_review`` entry to ``ai_daily_rankings.json``. That
entry is the sole source of truth for the public TOP3 and its track record.
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


def is_gpt_reviewed_day(day: dict) -> bool:
    """Require an explicit completed GPT review; never treat a screener row as AI."""
    analysis = day.get("analysis") or {}
    return (
        analysis.get("sourceType") == "gpt_screener_review"
        and analysis.get("status") == "complete"
        and bool(analysis.get("model"))
        and bool(analysis.get("candidateTradeDate"))
        and len(day.get("top3") or []) == 3
    )


def refresh_records(days: list[dict], screener: dict, existing: list[dict]) -> list[dict]:
    prices = {str(row.get("symbol") or "").upper(): number(row.get("price") or row.get("close")) for row in (screener.get("stocks") or [])}
    previous = {(str(row.get("recommendedDate") or ""), str(row.get("symbol") or "").upper(), int(number(row.get("rank")))): row for row in existing}
    records = []
    for day in sorted((row for row in days if is_gpt_reviewed_day(row)), key=lambda row: str(row.get("tradeDate") or "")):
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
                "analysisSource": "GPT 스크리너 재분석",
            })
    return records


def main() -> None:
    now = datetime.now(KST).isoformat(timespec="seconds")
    rankings = load_json(RANKING_PATH, {"days": []})
    recommendations = load_json(REC_PATH, {"recommendations": []})
    screener = load_json(SCREENER_PATH, {})
    days = rankings.get("days") or []
    records = refresh_records(days, screener, recommendations.get("recommendations") or [])
    latest = next((day for day in reversed(days) if is_gpt_reviewed_day(day)), None)
    REC_PATH.write_text(json.dumps({"updated": now, "recommendations": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RANKING_META_PATH.write_text(json.dumps({
        "updated": now,
        "tradeDate": (latest or {}).get("tradeDate"),
        "daysCount": len([day for day in days if is_gpt_reviewed_day(day)]),
        "source": "gpt_screener_review",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Refreshed {len(records)} track-record rows from GPT-reviewed TOP3 days")


if __name__ == "__main__":
    main()
