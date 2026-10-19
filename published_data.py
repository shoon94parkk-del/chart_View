"""Read published screener/PICK JSON from the latest GitHub main branch.

The stock screener writes validated JSON to GitHub Actions, but Render's static
files are baked into a deployment. This bounded remote reader makes published
selection prices visible without deploying the web service after every run.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

_DATA_DIR = Path(__file__).resolve().parent / "static" / "data"
_REMOTE_BASE = "https://raw.githubusercontent.com/shoon94parkk-del/chart_View/main/static/data"
_ALLOWED = {
    "ai_recommendations.json": "recommendations",
    "ai_daily_rankings.json": "days",
    "pick_monitor.json": "picks",
    "top10_history.json": "days",
    "screener.json": "stocks",
}
_LOCK = threading.RLock()
_CACHE: dict[str, tuple[float, dict, str]] = {}
_CACHE_TTL_SECONDS = 45.0


def _verified_payload(filename: str, content: bytes) -> dict:
    if len(content) > 12_000_000:
        raise ValueError("published data is too large")
    data = json.loads(content.decode("utf-8"))
    key = _ALLOWED[filename]
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise ValueError(f"invalid published data schema: {filename}")
    return data


def get_published_data(filename: str) -> tuple[dict, str]:
    """Returns (payload, source) with a short process-wide cache.

    The GitHub raw URL receives a rotating revision query key so a previous
    CDN copy does not remain pinned after a GitHub Actions commit. If GitHub is
    briefly unreachable, keep the most recent verified payload with its real
    as-of dates; never claim a fresh trading observation.
    """
    if filename not in _ALLOWED:
        raise ValueError("unapproved published data file")
    now = time.monotonic()
    with _LOCK:
        existing = _CACHE.get(filename)
        if existing and now < existing[0]:
            return existing[1], existing[2]

    local = _verified_payload(filename, (_DATA_DIR / filename).read_bytes())
    selected, source = local, "deployment-fallback"
    try:
        revision = int(time.time() // _CACHE_TTL_SECONDS)
        url = f"{_REMOTE_BASE}/{filename}?revision={revision}"
        request = Request(url, headers={
            "User-Agent": "ChartView-Published-Reader/1.0",
            "Cache-Control": "no-cache",
            "Accept": "application/json",
        })
        with urlopen(request, timeout=4.5) as response:
            remote = _verified_payload(filename, response.read(12_000_001))
        # A newly-deployed copy may be newer than GitHub's transient CDN copy.
        if str(remote.get("updated") or remote.get("generatedAt") or "") >= str(local.get("updated") or local.get("generatedAt") or ""):
            selected, source = remote, "github-main"
    except Exception:
        # The previous valid remote snapshot is better than reverting the UI
        # to an older deployment when a transient CDN/network error occurs.
        if existing and str(existing[1].get("updated") or existing[1].get("generatedAt") or "") >= str(local.get("updated") or local.get("generatedAt") or ""):
            selected, source = existing[1], "cached-published-fallback"

    with _LOCK:
        _CACHE[filename] = (time.monotonic() + (_CACHE_TTL_SECONDS if source == "github-main" else 12.0), selected, source)
    return selected, source
