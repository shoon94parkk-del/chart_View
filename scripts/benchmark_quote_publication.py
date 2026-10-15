#!/usr/bin/env python3
"""Controlled local ASGI quote-publication benchmark; no live providers.

Each timed trial runs the full actual app from a git archive in its own process.
The only runtime substitutions are deterministic fake provider/cache fixtures,
a denied-network guard and a transparent observer around the real publisher.
Imports and one provider-free Home warmup are excluded from timed intervals.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from contextlib import redirect_stdout


FAST = "005930.KS"
SLOW = "000660.KS"
OTHER = "IBM"
ORDER = [SLOW, FAST, OTHER]
OLD_ASOF = "2026-10-15T00:00:00+00:00"
NEW_ASOF = "2026-10-15T00:00:30+00:00"
SCENARIOS = {
    "mixed_ordinary": {"fresh": False, "slow": True},
    "mixed_fresh": {"fresh": True, "slow": True},
    "all_fast_fresh": {"fresh": True, "slow": False},
}


def quote(ticker, price, asof):
    return {
        "ticker": ticker, "name": ticker, "price": price,
        "previousClose": price - 1, "change": 1.0,
        "currency": "KRW" if ticker.endswith(".KS") else "USD",
        "asOf": asof, "sessionDate": asof[:10],
        "previousSessionDate": "2026-10-14",
        "source": "controlled fake canonical provider", "stale": False,
    }


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


async def worker_trial(args, main, httpx):
    scenario = SCENARIOS[args.scenario]
    old_epoch = time.time() - 3600
    old_rows = {FAST: quote(FAST, 100, OLD_ASOF), SLOW: quote(SLOW, 200, OLD_ASOF)}
    new_rows = {
        FAST: quote(FAST, 105, NEW_ASOF), SLOW: quote(SLOW, 205, NEW_ASOF),
        OTHER: quote(OTHER, 305, NEW_ASOF),
    }
    assert FAST in main.HOME_MAJOR_TICKERS and SLOW in main.HOME_MAJOR_TICKERS
    assert OTHER not in main.HOME_MAJOR_TICKERS
    main.HOME_LIVE_CACHE = {
        "quotes": deepcopy(old_rows), "updatedAt": OLD_ASOF,
        "marketUpdatedAt": {"KR": OLD_ASOF, "US": None},
        "marketUpdatedEpoch": {"KR": old_epoch, "US": 0.0},
        "quoteUpdatedEpoch": {ticker: old_epoch for ticker in old_rows},
        "refreshing": False, "lastError": None, "source": "controlled fixture",
    }
    main.HOME_LIVE_WAKE_EVENT = None
    # Deterministic market classification, matching the nearby runtime tests.
    main._open_home_markets = lambda *unused: {"KR": [FAST, SLOW]}
    provider_events = []
    event_lock = threading.Lock()
    publications = []
    original_publisher = main._publish_home_quote

    def observed_publisher(ticker, row, started_at):
        accepted = original_publisher(ticker, row, started_at)
        publications.append({"ticker": ticker, "at": time.perf_counter(), "accepted": accepted})
        return accepted

    main._publish_home_quote = observed_publisher

    def provider(ticker):
        started = time.perf_counter()
        delay = args.slow_ms if ticker == SLOW and scenario["slow"] else args.fast_ms
        time.sleep(delay / 1000)
        result = deepcopy(new_rows[ticker])
        finished = time.perf_counter()
        with event_lock:
            provider_events.append({"ticker": ticker, "start": started, "done": finished,
                                    "configured_delay_ms": delay})
        return result

    main.fetch_quote_snapshot = provider
    route_trace = {}
    measured = False

    async def observed_app(scope, receive, send):
        if measured and scope.get("path") == "/api/quotes":
            route_trace["scope_start"] = time.perf_counter()

            async def observed_send(message):
                if message["type"] == "http.response.start":
                    route_trace["response_start"] = time.perf_counter()
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    route_trace["body_complete"] = time.perf_counter()
                await send(message)

            await main.app(scope, receive, observed_send)
        else:
            await main.app(scope, receive, send)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=observed_app),
                                 base_url="http://benchmark.invalid") as client:
        warmup = await client.get("/api/home-live")
        assert warmup.status_code == 200
        assert {row["ticker"]: row for row in warmup.json()["results"]} == old_rows
        assert not provider_events
        measured = True
        t0 = time.perf_counter()
        completion = {}

        async def request_batch():
            response = await client.get("/api/quotes", params={
                "tickers": f"{SLOW},{FAST.lower()},{OTHER},{SLOW}",
                "fresh": str(scenario["fresh"]).lower(),
            })
            completion["at"] = time.perf_counter()
            return response

        batch = asyncio.create_task(request_batch())
        polls = 0
        home_durations_ms = []
        seen_fast = None
        visible_home = None
        batch_done_when_visible = None
        while seen_fast is None:
            poll_start = time.perf_counter()
            home = await client.get("/api/home-live")
            poll_end = time.perf_counter()
            polls += 1
            home_durations_ms.append((poll_end - poll_start) * 1000)
            assert home.status_code == 200
            assert home.headers["cache-control"] == "no-store"
            rows = {row["ticker"]: row for row in home.json()["results"]}
            if rows[FAST] == new_rows[FAST]:
                seen_fast = poll_end
                visible_home = rows
                batch_done_when_visible = batch.done()
                break
            assert rows[FAST] == old_rows[FAST]
            if poll_end - t0 > max(5, (args.slow_ms + 2 * args.poll_ms) / 1000):
                raise AssertionError("fast Home quote never became visible")
            if args.cadence_check:
                # Fixed phase at 0/5/10 seconds models the existing interval.
                await asyncio.sleep(max(0, t0 + polls * args.poll_ms / 1000 - time.perf_counter()))
            else:
                await asyncio.sleep(args.poll_ms / 1000)

        response = await asyncio.wait_for(batch, 5)
        assert response.status_code == 200
        payload = response.json()
        assert payload["results"] == [new_rows[ticker] for ticker in ORDER]
        assert payload["errors"] == []
        assert payload["providerFetches"] == 3 and payload["sharedCacheHits"] == 0
        assert payload["freshRequested"] is scenario["fresh"]
        assert Counter(event["ticker"] for event in provider_events) == Counter(ORDER)
        assert all(item["accepted"] for item in publications)
        assert Counter(item["ticker"] for item in publications) == Counter([FAST, SLOW])
        assert OTHER not in main.HOME_LIVE_CACHE["quotes"]
        assert main.HOME_LIVE_CACHE["marketUpdatedEpoch"]["KR"] == old_epoch
        final_home_response = await client.get("/api/home-live")
        final_home = {row["ticker"]: row for row in final_home_response.json()["results"]}
        assert final_home == {FAST: new_rows[FAST], SLOW: new_rows[SLOW]}

    normalized = dict(payload)
    del normalized["fetchedAt"]
    events = {event["ticker"]: event for event in provider_events}
    published = {item["ticker"]: item["at"] for item in publications}
    def ms(value):
        return round(value * 1000, 6)
    relative_events = [{
        "ticker": event["ticker"], "start_ms": ms(event["start"] - t0),
        "done_ms": ms(event["done"] - t0),
        "actual_provider_ms": ms(event["done"] - event["start"]),
        "configured_delay_ms": event["configured_delay_ms"],
    } for event in sorted(provider_events, key=lambda item: item["start"])]
    metrics = {
        "first_fast_home_visible_ms": ms(seen_fast - t0),
        "full_batch_client_ms": ms(completion["at"] - t0),
        "full_batch_asgi_ms": ms(route_trace["body_complete"] - route_trace["scope_start"]),
        "fast_provider_start_ms": ms(events[FAST]["start"] - t0),
        "fast_provider_duration_ms": ms(events[FAST]["done"] - events[FAST]["start"]),
        "fast_provider_done_ms": ms(events[FAST]["done"] - t0),
        "fast_publish_ms": ms(published[FAST] - t0),
        "fast_provider_done_to_publish_ms": ms(published[FAST] - events[FAST]["done"]),
        "fast_publish_to_home_visible_ms": ms(seen_fast - published[FAST]),
        "route_start_to_first_provider_start_ms": ms(min(e["start"] for e in provider_events) - route_trace["scope_start"]),
        "last_provider_done_to_response_body_ms": ms(route_trace["body_complete"] - max(e["done"] for e in provider_events)),
        "home_read_median_ms": round(statistics.median(home_durations_ms), 6),
        "home_read_max_ms": round(max(home_durations_ms), 6),
    }
    return {
        "scenario": args.scenario, "metrics": metrics,
        "provider_count": len(provider_events), "home_polls_until_visible": polls,
        "batch_done_when_fast_visible": batch_done_when_visible,
        "slow_price_when_fast_visible": visible_home[SLOW]["price"],
        "response_semantics_sha256": sha256(canonical(normalized).encode()),
        "response_semantics": normalized,
        "final_home_rows": final_home, "provider_events": relative_events,
        "publications": [{"ticker": item["ticker"], "at_ms": ms(item["at"] - t0),
                          "accepted": item["accepted"]} for item in publications],
    }


def worker(args):
    # Block network before app import; no credentials are passed by controller.
    def forbidden_network(*unused, **kwargs):
        raise AssertionError("benchmark attempted external network access")
    socket.socket.connect = forbidden_network
    import requests
    requests.sessions.Session.request = forbidden_network
    os.chdir(args.worker_source)
    sys.path.insert(0, args.worker_source)
    with redirect_stdout(io.StringIO()):
        import main
        import httpx
    result = asyncio.run(worker_trial(args, main, httpx))
    result["versions"] = {"python": platform.python_version(), "httpx": httpx.__version__}
    print(json.dumps(result, ensure_ascii=False))


def stats(values):
    ordered = sorted(values)
    return {"n": len(ordered), "min": min(ordered), "median": statistics.median(ordered),
            "p95_nearest_rank": ordered[max(0, math.ceil(.95 * len(ordered)) - 1)],
            "max": max(ordered)}


def archive(repo, revision, destination):
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", revision], text=True).strip()
    archive_path = destination.with_suffix(".tar")
    with archive_path.open("wb") as stream:
        subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", revision],
                       stdout=stream, check=True)
    destination.mkdir()
    with tarfile.open(archive_path) as bundle:
        bundle.extractall(destination, filter="data")
    archive_path.unlink()
    return {"revision": revision, "main_py_sha256": sha256((destination / "main.py").read_bytes())}


def markdown(result):
    lines = [
        "# Controlled local quote publication benchmark", "",
        f"Before: `{result['sources']['before']['revision']}`. After: `{result['sources']['after']['revision']}`.",
        "", "Actual archived FastAPI apps, in-process ASGI HTTP, synthetic dated quote rows, no lifespan or external network.",
        "Every trial uses a fresh subprocess and stale two-row Home fixture. Imports and an initial Home read are excluded; default-executor scheduling is included and separately recorded.",
        f"{result['config']['repetitions']} repetitions per version/scenario, alternating before/after order. Fake providers sleep {result['config']['fast_ms']} ms, with one {result['config']['slow_ms']} ms sibling in mixed cases. Home polling interval parameter: {result['config']['poll_ms']} ms; actual read timings are recorded.",
        "", "| Scenario | Version | First fresh fast Home row, median [min–max] ms | Full batch, median [min–max] ms | Fast provider done → publish, median ms |", "|---|---|---:|---:|---:|",
    ]
    for scenario in result["summary"]:
        for version in ("before", "after"):
            item = result["summary"][scenario][version]
            visible = item["first_fast_home_visible_ms"]
            batch = item["full_batch_client_ms"]
            lag = item["fast_provider_done_to_publish_ms"]["median"]
            lines.append(f"| {scenario} | {version} | {visible['median']:.2f} [{visible['min']:.2f}–{visible['max']:.2f}] | {batch['median']:.2f} [{batch['min']:.2f}–{batch['max']:.2f}] | {lag:.2f} |")
    lines.extend(["", "| Scenario | Paired median earlier Home visibility, ms | Relative reduction of version medians |", "|---|---:|---:|"])
    for scenario, item in result["paired_comparison"].items():
        lines.append(f"| {scenario} | {item['first_visibility_delta_ms']['median']:.2f} | {item['first_visibility_median_reduction_percent']:.2f}% |")
    lines.extend([
        "", "All trials returned the same ordered quote rows, error list, counters, fresh flag, source and data contract across versions after excluding only volatile `fetchedAt`. Each batch made exactly three provider calls despite duplicate/lowercase request symbols. Final Home rows matched; the non-Home symbol was never inserted. Market-level completion metadata was left unchanged.",
        "", "Mixed after trials expose the fast row while the original batch remains pending and the slow Home row remains old. The full `/api/quotes` response still waits for the slow sibling; this is an earlier shared-Home visibility improvement, not faster provider work or full-batch acceleration.",
        "", "The detailed JSON separates provider start/sleep duration, provider completion → publisher lag, publisher → Home polling lag, route scheduling and final response overhead. Polling resolution and instrumentation add local overhead; sub-millisecond/control differences should not be treated as production gains.",
        "", "Existing Home code (`static/js/home_heatmap_v57.js`, `LIVE_QUOTE_POLL_MS = 5_000`) reads on a roughly five-second interval. The 2 ms experiment measures cache visibility, not this client cadence or a rendered screen. If both a 40 ms fast quote and its 400 ms sibling complete before the next five-second poll, users may see no earlier update. A visible benefit requires a Home read to fall between the fast completion and the held sibling's completion; polling phase matters.",
        "", "This is controlled local code-path evidence. It does not measure mobile rendering, actual provider variability, Render CPU saturation/cold starts, live network latency, user incidents or a production SLA. No production call, deployment, runtime source change or data update is made by this harness.",
        "", "Reproduce:", "", "```bash", result["reproduce_command"], "```", "",
    ])
    if result["config"].get("cadence_check"):
        lines[0] = "# Controlled local check at existing Home polling cadence"
        lines[7:7] = ["", "This separate scenario models fixed-phase Home reads at 0/5/10 seconds with a synthetic six-second sibling. The phase is chosen to straddle fast and slow completion and demonstrates that conditional opportunity; it is not a prediction of every user's timing."]
    return "\n".join(lines)


def controller(args):
    repo = Path(args.repo).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    config = {"repetitions": args.repetitions, "fast_ms": args.fast_ms,
              "slow_ms": args.slow_ms, "poll_ms": args.poll_ms,
              "cadence_check": args.cadence_check}
    scenarios = ["mixed_fresh"] if args.cadence_check else list(SCENARIOS)
    records = []
    with tempfile.TemporaryDirectory(prefix="chartview-quote-benchmark-") as temporary:
        base = Path(temporary)
        sources = {version: archive(repo, revision, base / version)
                   for version, revision in (("before", args.before), ("after", args.after))}
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "TZ": "UTC",
               "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        for repetition in range(args.repetitions):
            versions = ("before", "after") if repetition % 2 == 0 else ("after", "before")
            for scenario in scenarios:
                for version in versions:
                    command = [sys.executable, str(script), "--worker-source", str(base / version),
                               "--scenario", scenario, "--fast-ms", str(args.fast_ms),
                               "--slow-ms", str(args.slow_ms), "--poll-ms", str(args.poll_ms)]
                    if args.cadence_check:
                        command.append("--cadence-check")
                    completed = subprocess.run(command, env=env, capture_output=True, text=True,
                                               check=True, timeout=30)
                    record = json.loads(completed.stdout)
                    record.update({"version": version, "repetition": repetition + 1,
                                   "sequence": len(records) + 1})
                    records.append(record)
                print(f"completed pair {repetition + 1}/{args.repetitions}: {scenario}", flush=True)
    summary = {}
    paired = {}
    for scenario in scenarios:
        summary[scenario] = {}
        for version in ("before", "after"):
            selected = [row for row in records if row["scenario"] == scenario and row["version"] == version]
            summary[scenario][version] = {key: stats([row["metrics"][key] for row in selected])
                                          for key in selected[0]["metrics"]}
        deltas = []
        for repetition in range(1, args.repetitions + 1):
            pair = {row["version"]: row for row in records
                    if row["scenario"] == scenario and row["repetition"] == repetition}
            assert pair["before"]["response_semantics"] == pair["after"]["response_semantics"]
            assert pair["before"]["final_home_rows"] == pair["after"]["final_home_rows"]
            if SCENARIOS[scenario]["slow"]:
                assert pair["after"]["batch_done_when_fast_visible"] is False
                assert pair["after"]["slow_price_when_fast_visible"] == 200
            deltas.append(pair["before"]["metrics"]["first_fast_home_visible_ms"] - pair["after"]["metrics"]["first_fast_home_visible_ms"])
        before = summary[scenario]["before"]["first_fast_home_visible_ms"]["median"]
        after = summary[scenario]["after"]["first_fast_home_visible_ms"]["median"]
        paired[scenario] = {"first_visibility_delta_ms": stats(deltas),
                            "first_visibility_median_reduction_percent": 100 * (before - after) / before}
    import shlex
    reproduction = ["env", "PYTHONDONTWRITEBYTECODE=1", sys.executable, str(script),
                    "--repo", str(repo), "--before", sources["before"]["revision"],
                    "--after", sources["after"]["revision"], "--repetitions", str(args.repetitions),
                    "--fast-ms", str(args.fast_ms), "--slow-ms", str(args.slow_ms),
                    "--poll-ms", str(args.poll_ms), "--output-dir", str(output)]
    if args.cadence_check:
        reproduction.append("--cadence-check")
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "kind": "controlled_local_asgi_not_mobile_or_live_sla", "sources": sources,
              "config": config, "summary": summary, "paired_comparison": paired,
              "response_semantics_parity": True, "all_provider_counts": [3],
              "reproduce_command": shlex.join(reproduction), "trials": records}
    prefix = "cadence-results" if args.cadence_check else "results"
    (output / f"{prefix}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (output / f"{prefix}.md").write_text(markdown(result))
    print(f"wrote {output / f'{prefix}.json'} and {output / f'{prefix}.md'}")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo")
    parser.add_argument("--before")
    parser.add_argument("--after")
    parser.add_argument("--output-dir")
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--fast-ms", type=float, default=40)
    parser.add_argument("--slow-ms", type=float, default=400)
    parser.add_argument("--poll-ms", type=float, default=2)
    parser.add_argument("--cadence-check", action="store_true",
                        help="Run only mixed fresh scenario; permit >=3 pairs and a client-scale poll interval")
    parser.add_argument("--worker-source", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", choices=list(SCENARIOS), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_source:
        worker(args)
    else:
        if not all((args.repo, args.before, args.after, args.output_dir)):
            parser.error("--repo, --before, --after and --output-dir are required")
        valid_delays = 0 < args.fast_ms < args.slow_ms and args.poll_ms > 0
        if args.cadence_check:
            if args.repetitions < 3 or not valid_delays:
                parser.error("cadence check requires repetitions >=3 and 0 < fast-ms < slow-ms and poll-ms >0")
        elif args.repetitions < 5 or not valid_delays or args.poll_ms >= args.fast_ms:
            parser.error("require repetitions >=5 and 0 < poll-ms < fast-ms < slow-ms")
        controller(args)


if __name__ == "__main__":
    cli()
