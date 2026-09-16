"""Refresh returns for GPT-reviewed daily TOP3 records.

This intentionally does *not* select stocks. The scheduled screener only
publishes a candidate universe. A separately scheduled GPT review commits a
completed ``gpt_screener_review`` entry to ``ai_daily_rankings.json``. That
entry is the sole source of truth for the public TOP3 and its track record.
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
    """Require an explicit completed GPT review; never treat a screener row as AI."""
    analysis = day.get("analysis") or {}
    return (
        analysis.get("sourceType") == "gpt_screener_review"
        and analysis.get("status") == "complete"
        and bool(analysis.get("model"))
        and bool(analysis.get("candidateTradeDate"))
        and len(day.get("top3") or []) == 3
    )


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


def refresh_records(days: list[dict], screener: dict, existing: list[dict]) -> list[dict]:
    by_symbol, by_name = _market_indexes(screener)
    previous = {
        (str(row.get("recommendedDate") or ""), str(row.get("symbol") or "").upper(), int(number(row.get("rank")))): row
        for row in existing
    }
    current_trade_date = str(screener.get("tradeDate") or screener.get("date") or "")
    records = []
    for day in sorted((row for row in days if is_gpt_reviewed_day(row)), key=lambda row: str(row.get("tradeDate") or "")):
        date = str(day.get("tradeDate") or "")
        for pick in (day.get("top3") or [])[:3]:
            symbol = str(pick.get("symbol") or "").upper()
            rank = int(number(pick.get("rank")))
            entry = number(pick.get("close"))
            market_row = _validate_pick_identity(pick, by_symbol, by_name)
            old = previous.get((date, symbol, rank), {})

            # A recommendation starts at 0% on its own recommendation date.
            # This also prevents small same-day provider differences from being
            # misrepresented as investment performance.
            current = entry if date == current_trade_date else number(market_row.get("price") or market_row.get("close"), entry)
            current_return = pct(current, entry)
            best = max(number(old.get("bestReturnPct"), current_return or 0), current_return or 0)
            records.append({
                "recommendedDate": date, "rank": rank, "symbol": symbol,
                "code": pick.get("code") or symbol.split(".", 1)[0], "name": pick.get("name") or symbol,
                "recommendedPrice": entry, "currentPrice": current, "returnPct": current_return,
                "bestReturnPct": round(best, 2),
                "lastUpdatedTradeDate": current_trade_date, "status": "tracking", "statusLabel": "성과 추적 중",
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
