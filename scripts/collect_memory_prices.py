"""Collect public latest prices directly and atomically publish validated history."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_price_publication import build_publication, validate_publication
from memory_spot_service import _fetch_latest_sync

DEFAULT_OUTPUT = ROOT / "static" / "data" / "memory_prices.json"
MAX_BYTES = 1_000_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate memory JSON field")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonstandard memory JSON number")


def _load_json(path: Path) -> dict:
    with path.open("rb") as source:
        content = source.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("memory publication is too large")
    return json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)


def _atomic_json(output: Path, publication: dict) -> None:
    serialized = json.dumps(publication, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", suffix=".tmp", delete=False) as target:
            temporary = Path(target.name)
            target.write(serialized)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def collect(output: Path = DEFAULT_OUTPUT, seed_history: Path | None = None, *, collected_at: str | None = None) -> dict:
    """Read durable prior state, fetch once, validate and atomically replace output.

    An initial seed is the actual existing API-v2 response, acquired at this job's
    timestamp. Its provider dates/values are retained without historical backfill.
    """
    output = Path(output)
    previous = None
    if output.exists():
        if seed_history is not None:
            raise ValueError("--seed-history is only valid for an initial publication")
        previous = validate_publication(_load_json(output))
    elif seed_history is not None:
        seed = _load_json(Path(seed_history))
        if not isinstance(seed, dict):
            raise ValueError("invalid memory API seed")
        acquired_at = collected_at or _utc_now()
        previous = validate_publication({**seed, "generatedAt": acquired_at, "collectedAt": acquired_at})
    latest = _fetch_latest_sync()
    publication = build_publication(previous, latest, collected_at=collected_at or _utc_now())
    _atomic_json(output, publication)
    return publication


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed-history", type=Path, help="Actual API-v2 JSON; initial publication only")
    parser.add_argument("--check", action="store_true", help="Validate saved output without fetching or writing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            if args.seed_history:
                raise ValueError("--check cannot seed history")
            publication = validate_publication(_load_json(args.output))
        else:
            publication = collect(args.output, seed_history=args.seed_history)
        print(json.dumps({"status": "valid" if args.check else "collected", "generatedAt": publication["generatedAt"],
                          "groups": len(publication["groups"]), "historyDates": len(publication["history"]),
                          "stale": publication["stale"]}))
        return 0
    except Exception as exc:
        # Never print response bodies or environment details in public Actions logs.
        print(f"Memory price publication failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
