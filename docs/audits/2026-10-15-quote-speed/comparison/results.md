# Controlled local quote publication benchmark

Before: `40daf4fd773e253839e23b9745ae6f34638b8c6b`. After: `3588790fff1fa8f4644c9172247400b1e64d6f71`.

Actual archived FastAPI apps, in-process ASGI HTTP, synthetic dated quote rows, no lifespan or external network.
Every trial uses a fresh subprocess and stale two-row Home fixture. Imports and an initial Home read are excluded; default-executor scheduling is included and separately recorded.
8 repetitions per version/scenario, alternating before/after order. Fake providers sleep 40.0 ms, with one 400.0 ms sibling in mixed cases. Home polling interval parameter: 2.0 ms; actual read timings are recorded.

| Scenario | Version | First fresh fast Home row, median [min–max] ms | Full batch, median [min–max] ms | Fast provider done → publish, median ms |
|---|---|---:|---:|---:|
| mixed_ordinary | before | 405.96 [404.77–408.35] | 404.25 [403.75–405.06] | 359.97 |
| mixed_ordinary | after | 46.69 [45.33–48.29] | 405.21 [404.49–409.46] | 0.22 |
| mixed_fresh | before | 406.34 [404.45–407.38] | 404.32 [403.96–404.90] | 360.04 |
| mixed_fresh | after | 46.74 [45.13–47.25] | 404.51 [404.02–408.93] | 0.19 |
| all_fast_fresh | before | 47.65 [45.86–49.51] | 44.95 [44.00–46.29] | 0.36 |
| all_fast_fresh | after | 46.91 [45.35–48.64] | 44.98 [44.50–45.82] | 0.19 |

| Scenario | Paired median earlier Home visibility, ms | Relative reduction of version medians |
|---|---:|---:|
| mixed_ordinary | 359.16 | 88.50% |
| mixed_fresh | 360.36 | 88.50% |
| all_fast_fresh | 0.20 | 1.55% |

All trials returned the same ordered quote rows, error list, counters, fresh flag, source and data contract across versions after excluding only volatile `fetchedAt`. Each batch made exactly three provider calls despite duplicate/lowercase request symbols. Final Home rows matched; the non-Home symbol was never inserted. Market-level completion metadata was left unchanged.

Mixed after trials expose the fast row while the original batch remains pending and the slow Home row remains old. The full `/api/quotes` response still waits for the slow sibling; this is an earlier shared-Home visibility improvement, not faster provider work or full-batch acceleration.

The detailed JSON separates provider start/sleep duration, provider completion → publisher lag, publisher → Home polling lag, route scheduling and final response overhead. Polling resolution and instrumentation add local overhead; sub-millisecond/control differences should not be treated as production gains.

Existing Home code (`static/js/home_heatmap_v57.js`, `LIVE_QUOTE_POLL_MS = 5_000`) reads on a roughly five-second interval. The 2 ms experiment measures cache visibility, not this client cadence or a rendered screen. If both a 40 ms fast quote and its 400 ms sibling complete before the next five-second poll, users may see no earlier update. A visible benefit requires a Home read to fall between the fast completion and the held sibling's completion; polling phase matters.

This is controlled local code-path evidence. It does not measure mobile rendering, actual provider variability, Render CPU saturation/cold starts, live network latency, user incidents or a production SLA. No production call, deployment, runtime source change or data update is made by this harness.

Reproduce:

```bash
env PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/chartview-backend-venv/bin/python /workspace/research/chartview-quote-speed-20261015/benchmark/quote_visibility_benchmark.py --repo /workspace/chartview-quote-speed-backend-20261015 --before 40daf4fd773e253839e23b9745ae6f34638b8c6b --after 3588790fff1fa8f4644c9172247400b1e64d6f71 --repetitions 8 --fast-ms 40.0 --slow-ms 400.0 --poll-ms 2.0 --output-dir /workspace/research/chartview-quote-speed-20261015/benchmark
```
