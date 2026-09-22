"""Validate the GitHub-published contract for a GPT-reviewed TOP3 day."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "static" / "data" / "ai_daily_rankings.json"
SCREENER_PATH = ROOT / "static" / "data" / "screener.json"
REQUIRED_SCORES = ("industryScore", "companyScore", "valuationScore", "catalystRiskScore", "technicalScore")


def number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_name(value: object) -> str:
    text = str(value or "").casefold().strip()
    return re.sub(r"[\s·・()\[\]㈜._-]+", "", text)


def build_identity_index(screener: dict) -> tuple[dict[str, dict], dict[str, list[str]]]:
    by_symbol: dict[str, dict] = {}
    by_name: dict[str, list[str]] = {}
    for row in screener.get("stocks") or []:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        by_symbol[symbol] = row
        key = normalize_name(row.get("name"))
        if key:
            by_name.setdefault(key, []).append(symbol)
    return by_symbol, by_name


def validate(day: dict, by_symbol: dict[str, dict] | None = None, by_name: dict[str, list[str]] | None = None) -> list[str]:
    errors: list[str] = []
    analysis = day.get("analysis") or {}
    date = str(day.get("tradeDate") or "")
    source_type = str(analysis.get("sourceType") or "")
    picks = day.get("top3") or []

    if source_type == "user_final_selection":
        if analysis.get("status") != "complete" or not analysis.get("model") or not analysis.get("candidateTradeDate"):
            errors.append(f"{date}: completed user final selection metadata is required")
        if analysis.get("candidateTradeDate") != date:
            errors.append(f"{date}: candidateTradeDate must match tradeDate")
        actual_ranks = [int(number(pick.get("rank"))) for pick in picks]
        if not (1 <= len(picks) <= 3) or actual_ranks != list(range(1, len(picks) + 1)):
            errors.append(f"{date}: user final selection must contain ranked 1..3 picks")
    elif source_type == "gpt_screener_review":
        if analysis.get("status") != "complete" or not analysis.get("model") or not analysis.get("candidateTradeDate"):
            errors.append(f"{date}: completed GPT model and candidateTradeDate are required")
        if analysis.get("candidateTradeDate") != date:
            errors.append(f"{date}: candidateTradeDate must match tradeDate")
        weights = (day.get("scorePolicy") or {}).get("weights") or {}
        if number(weights.get("companyGrowth")) <= number(weights.get("technical")):
            errors.append(f"{date}: companyGrowth weight must exceed technical weight")
        if len(picks) != 3 or [number(pick.get("rank")) for pick in picks] != [1, 2, 3]:
            errors.append(f"{date}: exactly ranked TOP3 is required")
    elif source_type:
        errors.append(f"{date}: unsupported analysis.sourceType {source_type}")
    else:
        # Historical PICK days published before analysis metadata was introduced.
        if len(picks) != 3 or [number(pick.get("rank")) for pick in picks] != [1, 2, 3]:
            errors.append(f"{date}: legacy published day must retain ranked TOP3")

    for pick in picks:
        symbol = str(pick.get("symbol") or "").upper()
        code = str(pick.get("code") or "")
        name = str(pick.get("name") or "")

        if not pick.get("reason") or not symbol or number(pick.get("close")) <= 0:
            errors.append(f"{date}: incomplete pick {pick.get('rank')}")
            continue

        if source_type == "gpt_screener_review":
            missing = [key for key in REQUIRED_SCORES if key not in pick]
            if missing:
                errors.append(f"{date}: incomplete pick {pick.get('rank')}")
                continue
            total = sum(number(pick.get(key)) for key in REQUIRED_SCORES)
            if round(total) != round(number(pick.get("totalScore"))):
                errors.append(f"{date}: score total mismatch for {symbol}")

        if code and code != symbol.split(".", 1)[0]:
            errors.append(f"{date}: code/symbol mismatch for {name}: code={code}, symbol={symbol}")

        if by_symbol is not None:
            row = by_symbol.get(symbol)
            expected_symbols = (by_name or {}).get(normalize_name(name), [])
            if row is None:
                hint = f"; expected={','.join(expected_symbols)}" if expected_symbols else ""
                errors.append(f"{date}: symbol not found for {name}: {symbol}{hint}")
            elif normalize_name(row.get("name")) != normalize_name(name):
                # Display-name aliases are accepted when the supplied name does
                # not resolve to a different known symbol (e.g. LS ELECTRIC vs 엘에스일렉트릭).
                conflicting = [candidate for candidate in expected_symbols if candidate != symbol]
                if conflicting:
                    errors.append(
                        f"{date}: identity mismatch: {symbol} is {row.get('name')}, not {name}; "
                        f"expected={','.join(conflicting)}"
                    )
    return errors


def main() -> None:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    screener = json.loads(SCREENER_PATH.read_text(encoding="utf-8"))
    by_symbol, by_name = build_identity_index(screener)
    errors = [error for day in payload.get("days") or [] for error in validate(day, by_symbol, by_name)]
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {len(payload.get('days') or [])} published PICK days with source-aware identity checks")


if __name__ == "__main__":
    main()
