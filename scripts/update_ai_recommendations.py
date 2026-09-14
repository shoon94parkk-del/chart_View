from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "static" / "data"
REC_PATH = DATA_DIR / "ai_recommendations.json"
SCREENER_PATH = DATA_DIR / "screener.json"


def load_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def pct(now: float, base: float) -> float | None:
    if not base:
        return None
    return round((now / base - 1.0) * 100.0, 2)


def main() -> None:
    payload = load_json(REC_PATH, {"updated": None, "recommendations": []})
    screener = load_json(SCREENER_PATH, {})
    stocks = screener.get("stocks") or []
    by_symbol = {str(r.get("symbol") or "").upper(): r for r in stocks}

    changed = False
    for rec in payload.get("recommendations") or []:
        if str(rec.get("status") or "active") == "closed":
            continue
        symbol = str(rec.get("symbol") or "").upper()
        row = by_symbol.get(symbol)
        if not row:
            continue
        current = row.get("price") or row.get("close")
        try:
            current = float(current)
            base = float(rec.get("recommendedPrice"))
        except (TypeError, ValueError):
            continue

        ret = pct(current, base)
        prev_best = rec.get("bestReturnPct")
        try:
            prev_best_f = float(prev_best)
        except (TypeError, ValueError):
            prev_best_f = ret if ret is not None else 0.0
        rec["currentPrice"] = current
        rec["returnPct"] = ret
        rec["bestReturnPct"] = max(prev_best_f, ret if ret is not None else prev_best_f)
        rec["lastUpdatedTradeDate"] = screener.get("tradeDate") or screener.get("date")
        changed = True

    payload["updated"] = datetime.now(KST).isoformat(timespec="seconds")
    if changed or not REC_PATH.exists():
        REC_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
