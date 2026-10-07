"""Save one already-complete canonical API response as a bounded warm seed.

No provider calls, fresh/force parameter, API key, or LLM is involved. The
default is ONE ordinary API request. Invalid/partial responses leave the last
snapshot unchanged. Requests keeps the inherited proxy and verified TLS.
"""
from __future__ import annotations

import argparse
import ast
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from heatmap_metadata import us_universe
from heatmap_snapshot import (MAX_SNAPSHOT_BYTES, SNAPSHOT_VERSION, SnapshotValidationError,
                              eligible_markets, validate_snapshot)

MAX_REQUESTS = 3
MAX_SECONDS = 60
DEFAULT_BASE_URL = "https://chart-view-pkv8.onrender.com"


def current_eligible(root: Path = ROOT) -> dict[str, str]:
    # Read only literal universe knobs, without importing the FastAPI app or
    # starting providers. This stays compatible with the requests-only workflow.
    constants = {}
    for node in ast.parse((root / "main.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"FULL_HEATMAP_KR_TICKERS", "FULL_HEATMAP_US_LIMIT"}:
                    constants[target.id] = ast.literal_eval(node.value)
    kr, limit = constants["FULL_HEATMAP_KR_TICKERS"], constants["FULL_HEATMAP_US_LIMIT"]
    if not isinstance(kr, list) or len(kr) != 20 or len(set(kr)) != 20 or limit != 40:
        raise SnapshotValidationError("review required: canonical universe budget changed")
    metadata = json.loads((root / "static/data/heatmap.json").read_text(encoding="utf-8"))
    us_rows = us_universe(metadata, {}, limit=limit)
    if len(us_rows) != limit:
        raise SnapshotValidationError("current US metadata does not provide 40 eligible symbols")
    return eligible_markets(kr, us_rows)


def save_snapshot(base_url: str, output: Path, *, attempts: int = 1,
                  session=None, eligible=None) -> dict:
    if not 1 <= attempts <= MAX_REQUESTS:
        raise ValueError("attempts must be between 1 and 3")
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment or parts.username:
        raise ValueError("base URL must be an HTTP(S) origin without credentials or query")
    if parts.path not in {"", "/"}:
        raise ValueError("base URL must be an origin")
    eligible = eligible if eligible is not None else current_eligible()
    session = session if session is not None else requests.Session()
    started = time.monotonic()
    errors = []
    for attempt in range(attempts):
        remaining = MAX_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            break
        try:
            with session.get(base_url.rstrip("/") + "/api/heatmap/full", timeout=(min(5, remaining), min(15, remaining)),
                             stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise SnapshotValidationError("canonical API must return HTTP 200 without redirect")
                content = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    content.extend(chunk)
                    if len(content) > MAX_SNAPSHOT_BYTES or time.monotonic() - started >= MAX_SECONDS:
                        raise SnapshotValidationError("response exceeds the capture size/time budget")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise SnapshotValidationError("canonical API must return an object")
            now = datetime.now(timezone.utc)
            captured = {**payload, "snapshotVersion": SNAPSHOT_VERSION,
                        "snapshotCapturedAt": now.isoformat()}
            # Validation marks warm-seed rows stale. The saved API response keeps
            # its original provenance/stale fields, while runtime always marks it stale.
            validate_snapshot(captured, eligible, now=now, require_complete=True)
            encoded = json.dumps(captured, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            output = Path(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(output.name + ".tmp")
            try:
                temporary.write_text(encoded, encoding="utf-8")
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
            return captured
        except (requests.RequestException, ValueError, UnicodeError) as exc:
            errors.append(f"request {attempt + 1}: {type(exc).__name__}: {exc}")
    raise SnapshotValidationError("no complete valid canonical response; existing snapshot preserved: " + "; ".join(errors))


def _deadline(_signum, _frame):
    raise TimeoutError("full heatmap snapshot exceeded the 60-second process budget")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", type=Path, default=ROOT / "static/data/full_heatmap_snapshot.json")
    parser.add_argument("--attempts", type=int, choices=range(1, MAX_REQUESTS + 1), default=1)
    args = parser.parse_args()
    # A hard Linux/GitHub Actions deadline also bounds slow/chunked HTTP bodies.
    signal.signal(signal.SIGALRM, _deadline)
    signal.alarm(MAX_SECONDS)
    try:
        result = save_snapshot(args.base_url, args.output, attempts=args.attempts)
    finally:
        signal.alarm(0)
    print(f"saved canonical warm seed: {result['counts']} (original generatedAt={result['generatedAt']})")


if __name__ == "__main__":
    main()
