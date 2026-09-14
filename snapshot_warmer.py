"""Background snapshot warmer for the public Render service.

The browser should never have to be the first caller that pays the cost of
refreshing Home.  On Render, keep the two shared Home snapshots warm every five
minutes.  Visitors still trigger the existing best-effort foreground refresh,
but they receive the last successful snapshot immediately first.

The worker is intentionally disabled outside Render so local development and CI
remain deterministic and do not call the production site.
"""
from __future__ import annotations

import os
import threading
import time
from urllib.parse import urljoin

import requests

WARM_INTERVAL_SEC = 300
INITIAL_DELAY_SEC = 18
REQUEST_TIMEOUT_SEC = 24

_started = False
_start_lock = threading.Lock()


def _base_url() -> str:
    return str(os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")


def _warm_once(base_url: str) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "ChartView-SnapshotWarmer/1.0", "Accept": "application/json"})
    targets = (
        "/api/market-now?fresh=1&source=server-preload",
        "/api/home-snapshot?fresh=1&source=server-preload",
    )
    for path in targets:
        started = time.monotonic()
        try:
            response = session.get(urljoin(f"{base_url}/", path.lstrip("/")), timeout=REQUEST_TIMEOUT_SEC)
            response.raise_for_status()
            payload = response.json()
            age = payload.get("cacheAgeSec") if isinstance(payload, dict) else None
            elapsed_ms = round((time.monotonic() - started) * 1000)
            print(f"[PRELOAD] {path.split('?')[0]} warmed in {elapsed_ms}ms cacheAge={age}")
        except Exception as exc:
            # Never kill the server because a provider is temporarily unavailable.
            print(f"[PRELOAD] {path.split('?')[0]} warm failed: {type(exc).__name__}: {exc}")


def _worker(base_url: str) -> None:
    # Let uvicorn finish binding the public service before the first self-request.
    time.sleep(INITIAL_DELAY_SEC)
    while True:
        cycle_started = time.monotonic()
        _warm_once(base_url)
        elapsed = time.monotonic() - cycle_started
        time.sleep(max(15.0, WARM_INTERVAL_SEC - elapsed))


def start_snapshot_warmer() -> bool:
    """Start one daemon worker on Render; return True only when it starts."""
    global _started
    base_url = _base_url()
    if not base_url:
        return False
    with _start_lock:
        if _started:
            return False
        _started = True
        thread = threading.Thread(
            target=_worker,
            args=(base_url,),
            name="chartview-snapshot-warmer",
            daemon=True,
        )
        thread.start()
        print(f"[PRELOAD] 5-minute snapshot warmer started for {base_url}")
        return True
