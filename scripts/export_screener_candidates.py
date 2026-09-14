from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "static" / "data" / "screener.json"
OUT = ROOT / "static" / "data" / "screener_top100.json"

payload = json.loads(SRC.read_text(encoding="utf-8"))
out = {k: payload.get(k) for k in ("updated", "tradeDate", "count", "universeCount", "scoreModel", "source")}
out["stocks"] = (payload.get("stocks") or [])[:100]
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Saved {len(out['stocks'])} candidates -> {OUT}")
