from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consensus_service import fetch_live_consensus

DATA = ROOT / "static" / "data"
VALUATION_CACHE = DATA / "valuation_cache.json"
OUT_CACHE = DATA / "consensus_cache.json"
OUT_HISTORY = DATA / "consensus_history.json"
MAX_HISTORY_DAYS = 180


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def selected_symbols() -> list[str]:
    payload = load_json(VALUATION_CACHE)
    quotes = payload.get("quotes") or {}
    symbols = [str(x).upper() for x in quotes.keys() if x]
    for symbol in ("AAPL", "NVDA", "005930.KS", "000660.KS"):
        if symbol not in symbols:
            symbols.append(symbol)
    return sorted(set(symbols))


def history_point(snapshot: dict, period: str) -> dict | None:
    row = (snapshot.get("periods") or {}).get(period) or {}
    earnings = row.get("earnings") or {}
    revenue = row.get("revenue") or {}
    eps = earnings.get("avg")
    sales = revenue.get("avg")
    if eps is None and sales is None:
        return None
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "eps": eps,
        "revenue": sales,
        "epsAnalysts": earnings.get("analysts"),
        "revenueAnalysts": revenue.get("analysts"),
    }


def prune(rows: list[dict]) -> list[dict]:
    rows = [x for x in rows if isinstance(x, dict) and x.get("date")]
    rows.sort(key=lambda x: x["date"])
    return rows[-MAX_HISTORY_DAYS:]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    old_history = load_json(OUT_HISTORY)
    history = old_history.get("history") or {}
    quotes: dict[str, dict] = {}
    errors: dict[str, str] = {}

    symbols = selected_symbols()
    for index, symbol in enumerate(symbols, start=1):
        try:
            row = fetch_live_consensus(symbol)
            quotes[symbol] = row
            for period in ("0y", "+1y"):
                point = history_point(row, period)
                if not point:
                    continue
                sym_hist = history.setdefault(symbol, {})
                rows = list(sym_hist.get(period) or [])
                if rows and rows[-1].get("date") == point["date"]:
                    rows[-1] = point
                else:
                    rows.append(point)
                sym_hist[period] = prune(rows)
            print(f"[{index}/{len(symbols)}] {symbol} OK")
        except Exception as exc:
            errors[symbol] = str(exc)
            print(f"[{index}/{len(symbols)}] {symbol} ERROR {exc}")
        time.sleep(0.08)

    generated = datetime.now(timezone.utc).isoformat()
    cache_payload = {
        "generatedAt": generated,
        "count": len(quotes),
        "errors": errors,
        "source": "Yahoo Finance earningsTrend",
        "quotes": quotes,
    }
    history_payload = {
        "generatedAt": generated,
        "retentionDays": MAX_HISTORY_DAYS,
        "history": history,
    }
    OUT_CACHE.write_text(json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUT_HISTORY.write_text(json.dumps(history_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(quotes)}/{len(symbols)} consensus snapshots; errors={len(errors)}")

    for symbol in ("AAPL", "NVDA", "005930.KS", "000660.KS"):
        if symbol not in quotes:
            raise SystemExit(f"required consensus missing: {symbol}: {errors.get(symbol)}")


if __name__ == "__main__":
    main()
