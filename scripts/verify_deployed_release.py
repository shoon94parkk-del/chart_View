"""Verify exact revision and content-addressed release assets, before/after UI tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("static/js/chartview_release_bundle.js", "static/css/chartview_release_bundle.css", "static/js/ai_daily_widget.js")


def get(base, path):
    request = Request(f"{base.rstrip('/')}/{path.lstrip('/')}", headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def health(base, expected):
    data = json.loads(get(base, f"health?revision_check={time.time_ns()}"))
    if data.get("status") != "ok" or data.get("revision") != expected:
        raise ValueError(f"Expected healthy revision {expected}; got {data.get('revision')} / {data.get('status')}")
    return data


def verify(base, expected, attempts=36, interval=10):
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("EXPECTED_SHA must be a full commit SHA")
    for attempt in range(attempts):
        try:
            health(base, expected)
            break
        except Exception as exc:
            print(f"Revision attempt {attempt + 1}/{attempts}: {exc}", flush=True)
            if attempt + 1 == attempts:
                raise
            time.sleep(interval)
    html = get(base, f"?release_check={time.time_ns()}").decode("utf-8")
    hashes = {}
    for asset in ASSETS:
        digest = hashlib.sha256((ROOT / asset).read_bytes()).hexdigest()
        url = f"/{asset}?v={digest[:12]}"
        if url not in html:
            raise ValueError(f"Served HTML does not reference tested asset: {url}")
        actual = hashlib.sha256(get(base, url)).hexdigest()
        if actual != digest:
            raise ValueError(f"Served asset mismatch: {asset}")
        hashes[asset] = digest
    health(base, expected)  # Reject a deploy that changed during verification.
    return {"revision": expected, "baseUrl": base, "assets": hashes, "verifiedAt": time.time()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=36)
    parser.add_argument("--output", default="test-results/release-verification.json")
    args = parser.parse_args()
    result = verify(os.environ.get("APP_URL", "https://chart-view-bsg6.onrender.com"), os.environ.get("EXPECTED_SHA", ""), args.attempts)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
