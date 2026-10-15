# Controlled local check at existing Home polling cadence

Before: `40daf4fd773e253839e23b9745ae6f34638b8c6b`. After: `3588790fff1fa8f4644c9172247400b1e64d6f71`.

Actual archived FastAPI apps, in-process ASGI HTTP, synthetic dated quote rows, no lifespan or external network.
Every trial uses a fresh subprocess and stale two-row Home fixture. Imports and an initial Home read are excluded; default-executor scheduling is included and separately recorded.
3 repetitions per version/scenario, alternating before/after order. Fake providers sleep 40.0 ms, with one 6000.0 ms sibling in mixed cases. Home polling interval parameter: 5000.0 ms; actual read timings are recorded.

This separate scenario models fixed-phase Home reads at 0/5/10 seconds with a synthetic six-second sibling. The phase is chosen to straddle fast and slow completion and demonstrates that conditional opportunity; it is not a prediction of every user's timing.

| Scenario | Version | First fresh fast Home row, median [min–max] ms | Full batch, median [min–max] ms | Fast provider done → publish, median ms |
|---|---|---:|---:|---:|
| mixed_fresh | before | 10018.27 [10016.01–10019.76] | 6006.93 [6005.32–6016.18] | 5961.47 |
| mixed_fresh | after | 5017.60 [5011.00–5020.72] | 6005.69 [6005.54–6007.18] | 0.28 |

| Scenario | Paired median earlier Home visibility, ms | Relative reduction of version medians |
|---|---:|---:|
| mixed_fresh | 4999.04 | 49.92% |

All trials returned the same ordered quote rows, error list, counters, fresh flag, source and data contract across versions after excluding only volatile `fetchedAt`. Each batch made exactly three provider calls despite duplicate/lowercase request symbols. Final Home rows matched; the non-Home symbol was never inserted. Market-level completion metadata was left unchanged.

Mixed after trials expose the fast row while the original batch remains pending and the slow Home row remains old. The full `/api/quotes` response still waits for the slow sibling; this is an earlier shared-Home visibility improvement, not faster provider work or full-batch acceleration.

The detailed JSON separates provider start/sleep duration, provider completion → publisher lag, publisher → Home polling lag, route scheduling and final response overhead. Polling resolution and instrumentation add local overhead; sub-millisecond/control differences should not be treated as production gains.

Existing Home code (`static/js/home_heatmap_v57.js`, `LIVE_QUOTE_POLL_MS = 5_000`) reads on a roughly five-second interval. The 2 ms experiment measures cache visibility, not this client cadence or a rendered screen. If both a 40 ms fast quote and its 400 ms sibling complete before the next five-second poll, users may see no earlier update. A visible benefit requires a Home read to fall between the fast completion and the held sibling's completion; polling phase matters.

This is controlled local code-path evidence. It does not measure mobile rendering, actual provider variability, Render CPU saturation/cold starts, live network latency, user incidents or a production SLA. No production call, deployment, runtime source change or data update is made by this harness.

Reproduce:

```bash
env PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/chartview-backend-venv/bin/python /workspace/research/chartview-quote-speed-20261015/benchmark/quote_visibility_benchmark.py --repo /workspace/chartview-quote-speed-backend-20261015 --before 40daf4fd773e253839e23b9745ae6f34638b8c6b --after 3588790fff1fa8f4644c9172247400b1e64d6f71 --repetitions 3 --fast-ms 40.0 --slow-ms 6000.0 --poll-ms 5000.0 --output-dir /workspace/research/chartview-quote-speed-20261015/benchmark --cadence-check
```
