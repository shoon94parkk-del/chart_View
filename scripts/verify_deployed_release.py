"""Verify exact revision, release assets and Guru publication before/after UI tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("static/js/chartview_release_bundle.js", "static/css/chartview_release_bundle.css", "static/js/ai_daily_widget.js")
GURU_CDN_BASE = "https://raw.githubusercontent.com/shoon94parkk-del/chart_View/main"
GURU_STRATEGIES = ("buffett", "lynch", "oneil", "minervini", "greenblatt")
GURU_COUNTS = ("unsupportedCount", "pendingCount", "insufficientCount", "failedCount", "matchedCount")


def get(base, path):
    request = Request(f"{base.rstrip('/')}/{path.lstrip('/')}", headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def health(base, expected):
    data = json.loads(get(base, f"health?revision_check={time.time_ns()}"))
    if data.get("status") != "ok" or data.get("revision") != expected:
        raise ValueError(f"Expected healthy revision {expected}; got {data.get('revision')} / {data.get('status')}")
    return data


def verify_guru_publication(base):
    """Read saved/public data only; this neither deploys nor collects provider data."""
    snapshot = json.loads((ROOT / "static/data/guru_screening.json").read_text(encoding="utf-8"))
    evidence = json.loads((ROOT / "static/data/guru_evidence.json").read_text(encoding="utf-8"))
    metadata = {key: snapshot.get(key) for key in ("snapshotVersion", "criteriaVersion", "tradeDate")}
    if not all(metadata.values()) or any(evidence.get(key) != value for key, value in metadata.items()):
        raise ValueError("Guru evidence metadata does not match the tested snapshot")
    strategies = snapshot.get("strategies") or {}
    if set(strategies) != set(GURU_STRATEGIES):
        raise ValueError("Guru strategies must include all five published coverage states")

    def check_snapshots():
        for label, source in (("backend", base), ("CDN", GURU_CDN_BASE)):
            current = json.loads(get(source, f"/static/data/guru_screening.json?publication_check={time.time_ns()}"))
            if current != snapshot:
                raise ValueError(f"Guru snapshot {label} differs from tested publication: "
                                 f"expected {metadata['snapshotVersion']}, got {current.get('snapshotVersion')}")

    check_snapshots()
    verified, responses = {}, {}
    for strategy in GURU_STRATEGIES:
        row = strategies[strategy]
        counts = {key: row.get(key) for key in (*GURU_COUNTS, "evaluatedCount", "universeCount")}
        results = row.get("results")
        if (any(type(value) is not int or value < 0 for value in counts.values())
                or not isinstance(results, list)
                or counts["universeCount"] != sum(counts[key] for key in GURU_COUNTS)
                or counts["evaluatedCount"] != counts["matchedCount"] + counts["failedCount"]
                or counts["matchedCount"] != len(results)):
            raise ValueError(f"Guru strategies have invalid coverage: {strategy}")
        for candidate in results:
            symbol = candidate.get("symbol", "")
            saved = evidence.get("companies", {}).get(symbol, {})
            if (not re.fullmatch(r"\d{6}\.(KS|KQ)", symbol) or candidate.get("evidenceKey") != symbol
                    or candidate.get("tradeDate") != metadata["tradeDate"] or saved.get("symbol") != symbol
                    or saved.get("strategies", {}).get(strategy, {}).get("status") != "matched"):
                raise ValueError(f"Guru evidence is missing or mismatched for {strategy}: {symbol}")
        report = {"coverage": counts, "missingReasons": row.get("missingReasons", {})}
        if not results:
            report["status"] = "no_matches" if counts["evaluatedCount"] else "unavailable"
        else:
            # Select a real candidate from this strategy; never invent a substitute for an empty list.
            symbol = results[0]["symbol"]
            if symbol not in responses:
                query = urlencode({"version": metadata["snapshotVersion"], "publication_check": time.time_ns()})
                responses[symbol] = json.loads(get(base, f"/api/guru-investing/{symbol}?{query}"))
            expected = {**evidence["companies"][symbol], **metadata}
            if responses[symbol] != expected:
                raise ValueError(f"Guru evidence API differs from tested publication for {strategy}: {symbol}")
            report.update(status="evidence_verified", symbol=symbol)
        verified[strategy] = report

    rejection = "not_checked_no_candidates"
    if responses:
        symbol = next(iter(responses))
        # A deliberately non-current version tests the existing fail-closed API contract.
        version = "0" * 20 if metadata["snapshotVersion"] != "0" * 20 else "1" * 20
        query = urlencode({"version": version, "publication_check": time.time_ns()})
        try:
            get(base, f"/api/guru-investing/{symbol}?{query}")
        except HTTPError as exc:
            if exc.code != 409:
                raise ValueError(f"Guru non-current version returned HTTP {exc.code}, expected 409") from None
            detail = json.loads(exc.read()).get("detail", {})
            if detail.get("code") != "snapshot_changed" or detail.get("currentVersion") != metadata["snapshotVersion"]:
                raise ValueError("Guru non-current version rejection reports another publication")
            rejection = "verified_409"
        else:
            raise ValueError("Guru non-current version was accepted instead of returning 409")
    check_snapshots()  # A data publish can change CDN without changing Render's revision.
    return {**metadata, "generatedAt": snapshot.get("generatedAt"), "strategies": verified,
            "nonCurrentVersionRejection": rejection}


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
    guru = verify_guru_publication(base)
    health(base, expected)  # Reject a deploy that changed during verification.
    return {"revision": expected, "baseUrl": base, "assets": hashes, "guru": guru, "verifiedAt": time.time()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=36)
    parser.add_argument("--output", default="test-results/release-verification.json")
    args = parser.parse_args()
    result = verify(os.environ.get("APP_URL", "https://chart-view-pkv8.onrender.com"), os.environ.get("EXPECTED_SHA", ""), args.attempts)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
