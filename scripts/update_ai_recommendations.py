"""Refresh public ChartView PICK returns from the latest screener prices.

The screener chooses no stocks here. This script only reprices TOP3 days that
were already explicitly finalized, or legacy days that already exist in the
public recommendation ledger. This keeps the recommendation-date close fixed
while updating current price and performance to the latest screener trade date.
"""
from __future__ import annotations

import json
import re
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


def normalize_name(value: object) -> str:
    text = str(value or "").casefold().strip()
    return re.sub(r"[\s·・()\[\]㈜._-]+", "", text)


def is_gpt_reviewed_day(day: dict) -> bool:
    """Return True only for an explicitly completed GPT screener review."""
    analysis = day.get("analysis") or {}
    return (
        analysis.get("sourceType") == "gpt_screener_review"
        and analysis.get("status") == "complete"
        and bool(analysis.get("model"))
        and bool(analysis.get("candidateTradeDate"))
        and len(day.get("top3") or []) == 3
    )


def is_user_final_selection_day(day: dict) -> bool:
    """A user-confirmed final TOP3 is also a published track-record day."""
    analysis = day.get("analysis") or {}
    date = str(day.get("tradeDate") or "")
    return (
        analysis.get("sourceType") == "user_final_selection"
        and analysis.get("status") == "complete"
        and bool(analysis.get("model"))
        and str(analysis.get("candidateTradeDate") or "") == date
        and len(day.get("top3") or []) == 3
    )


def is_explicit_final_day(day: dict) -> bool:
    return is_gpt_reviewed_day(day) or is_user_final_selection_day(day)


def _record_key(date: str, pick: dict) -> tuple[str, str, int]:
    return (
        str(date or ""),
        str(pick.get("symbol") or "").upper(),
        int(number(pick.get("rank"))),
    )


def _is_legacy_published_day(day: dict, previous: dict[tuple[str, str, int], dict]) -> bool:
    """Keep repricing historical days that were already publicly committed."""
    picks = day.get("top3") or []
    date = str(day.get("tradeDate") or "")
    if not date or len(picks) != 3:
        return False
    return all(_record_key(date, pick) in previous for pick in picks)


def is_trackable_day(day: dict, previous: dict[tuple[str, str, int], dict]) -> bool:
    return is_explicit_final_day(day) or _is_legacy_published_day(day, previous)


def _market_indexes(screener: dict) -> tuple[dict[str, dict], dict[str, list[str]]]:
    by_symbol: dict[str, dict] = {}
    by_name: dict[str, list[str]] = {}
    for row in screener.get("stocks") or []:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        by_symbol[symbol] = row
        name_key = normalize_name(row.get("name"))
        if name_key:
            by_name.setdefault(name_key, []).append(symbol)
    return by_symbol, by_name


def _validate_pick_identity(pick: dict, by_symbol: dict[str, dict], by_name: dict[str, list[str]]) -> dict:
    symbol = str(pick.get("symbol") or "").upper()
    code = str(pick.get("code") or "")
    name = str(pick.get("name") or "")
    row = by_symbol.get(symbol)
    expected_symbols = by_name.get(normalize_name(name), [])

    if row is None:
        hint = f"; expected symbol for {name!r}: {', '.join(expected_symbols)}" if expected_symbols else ""
        raise ValueError(f"TOP3 symbol not found in screener: {symbol}{hint}")
    if normalize_name(row.get("name")) != normalize_name(name):
        hint = f"; expected symbol for {name!r}: {', '.join(expected_symbols)}" if expected_symbols else ""
        raise ValueError(
            f"TOP3 identity mismatch: {symbol} is {row.get('name')!r}, not {name!r}{hint}"
        )
    symbol_code = symbol.split(".", 1)[0]
    if code and code != symbol_code:
        raise ValueError(f"TOP3 code/symbol mismatch: code={code}, symbol={symbol}")
    return row


def _source_label(day: dict) -> str:
    source_type = str((day.get("analysis") or {}).get("sourceType") or "")
    if source_type == "user_final_selection":
        return "사용자 최종 선택"
    if source_type == "gpt_screener_review":
        return "GPT 스크리너 재분석"
    return "기존 공개 기록"


def refresh_records(days: list[dict], screener: dict, existing: list[dict]) -> list[dict]:
    by_symbol, by_name = _market_indexes(screener)
    previous = {
        (
            str(row.get("recommendedDate") or ""),
            str(row.get("symbol") or "").upper(),
            int(number(row.get("rank"))),
        ): row
        for row in existing
    }
    current_trade_date = str(screener.get("tradeDate") or screener.get("date") or "")
    records = []
    eligible_days = [row for row in days if is_trackable_day(row, previous)]

    for day in sorted(eligible_days, key=lambda row: str(row.get("tradeDate") or "")):
        date = str(day.get("tradeDate") or "")
        for pick in (day.get("top3") or [])[:3]:
            symbol = str(pick.get("symbol") or "").upper()
            rank = int(number(pick.get("rank")))
            entry = number(pick.get("close"))
            market_row = _validate_pick_identity(pick, by_symbol, by_name)
            old = previous.get((date, symbol, rank), {})

            # A recommendation starts at 0% on its own recommendation date.
            # For older picks, use the current screener trade-date price so the
            # ledger cannot silently remain on yesterday's value.
            current = entry if date == current_trade_date else number(
                market_row.get("price") or market_row.get("close"), entry
            )
            current_return = pct(current, entry)
            best = max(number(old.get("bestReturnPct"), current_return or 0), current_return or 0)
            score = old.get("score") if old.get("score") is not None else pick.get("totalScore")
            records.append({
                "recommendedDate": date,
                "rank": rank,
                "symbol": symbol,
                "code": pick.get("code") or symbol.split(".", 1)[0],
                "name": pick.get("name") or symbol,
                "recommendedPrice": entry,
                "currentPrice": current,
                "returnPct": current_return,
                "bestReturnPct": round(best, 2),
                "lastUpdatedTradeDate": current_trade_date,
                "status": old.get("status") or "tracking",
                "statusLabel": old.get("statusLabel") or "성과 추적 중",
                "grade": old.get("grade") or pick.get("grade") or "관찰",
                "reason": old.get("reason") or pick.get("reason") or "",
                "score": score,
                "analysisSource": old.get("analysisSource") or _source_label(day),
            })
    return records


def main() -> None:
    now = datetime.now(KST).isoformat(timespec="seconds")
    rankings = load_json(RANKING_PATH, {"days": []})
    recommendations = load_json(REC_PATH, {"recommendations": []})
    screener = load_json(SCREENER_PATH, {})
    days = rankings.get("days") or []
    existing = recommendations.get("recommendations") or []
    records = refresh_records(days, screener, existing)
    previous = {
        (
            str(row.get("recommendedDate") or ""),
            str(row.get("symbol") or "").upper(),
            int(number(row.get("rank"))),
        ): row
        for row in existing
    }
    trackable_days = [day for day in days if is_trackable_day(day, previous)]
    latest = max(trackable_days, key=lambda day: str(day.get("tradeDate") or ""), default=None)
    latest_source = str(((latest or {}).get("analysis") or {}).get("sourceType") or "published_top3")

    REC_PATH.write_text(
        json.dumps({"updated": now, "recommendations": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    RANKING_META_PATH.write_text(
        json.dumps({
            "updated": now,
            "tradeDate": (latest or {}).get("tradeDate"),
            "daysCount": len(trackable_days),
            "source": latest_source,
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Refreshed {len(records)} public PICK rows to screener trade date "
        f"{screener.get('tradeDate') or screener.get('date')}"
    )


if __name__ == "__main__":
    main()
