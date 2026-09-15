"""Validate the GitHub-published contract for a GPT-reviewed TOP3 day."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "static" / "data" / "ai_daily_rankings.json"
REQUIRED_SCORES = ("industryScore", "companyScore", "valuationScore", "catalystRiskScore", "technicalScore")


def number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def validate(day: dict) -> list[str]:
    errors: list[str] = []
    analysis = day.get("analysis") or {}
    date = str(day.get("tradeDate") or "")
    if analysis.get("sourceType") != "gpt_screener_review":
        errors.append(f"{date}: analysis.sourceType must be gpt_screener_review")
    if analysis.get("status") != "complete" or not analysis.get("model") or not analysis.get("candidateTradeDate"):
        errors.append(f"{date}: completed GPT model and candidateTradeDate are required")
    if analysis.get("candidateTradeDate") != date:
        errors.append(f"{date}: candidateTradeDate must match tradeDate")
    weights = (day.get("scorePolicy") or {}).get("weights") or {}
    if number(weights.get("companyGrowth")) <= number(weights.get("technical")):
        errors.append(f"{date}: companyGrowth weight must exceed technical weight")
    picks = day.get("top3") or []
    if len(picks) != 3 or [number(pick.get("rank")) for pick in picks] != [1, 2, 3]:
        errors.append(f"{date}: exactly ranked TOP3 is required")
    for pick in picks:
        missing = [key for key in REQUIRED_SCORES if key not in pick]
        if missing or not pick.get("reason") or not pick.get("symbol") or number(pick.get("close")) <= 0:
            errors.append(f"{date}: incomplete pick {pick.get('rank')}")
            continue
        total = sum(number(pick.get(key)) for key in REQUIRED_SCORES)
        if round(total) != round(number(pick.get("totalScore"))):
            errors.append(f"{date}: score total mismatch for {pick.get('symbol')}")
    return errors


def main() -> None:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    errors = [error for day in payload.get("days") or [] for error in validate(day)]
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {len(payload.get('days') or [])} GPT-reviewed TOP3 days")


if __name__ == "__main__":
    main()
