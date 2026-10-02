# No-repeat regression policy

Last updated: 2026-10-02

This backend has several production optimizations that were already solved once. Do not rely on chat memory and do not treat a repeated slowdown as a brand-new subsystem.

## Mandatory pre-edit check
Before changing quotes, Home live cache, compare/valuation, valuation-band, heatmap, startup warming, provider calls, or request executors:

1. Search `docs/decision-log.md`, `docs/regression-guardrails.md`, `docs/project-memory.md`, tests, and recent commits for the same symptom.
2. Classify the task as new behavior, new bug, or regression.
3. For a regression, restore the known-good contract first; do not add a second competing cache/refresh path.
4. Identify and run the existing regression test. Strengthen/add a test if the repeated issue escaped.
5. Verify the exact deployed SHA and production behavior. Render status alone is insufficient.
6. Never improve apparent latency by weakening quote freshness or changing historical/current semantics.

## Known-good contracts

### Quotes
- `/api/home-live` stays provider-free on the request path and returns shared memory immediately.
- Background provider refresh stays on the background market executor.
- `/api/quotes?fresh=true` is the canonical direct fresh revalidation path and must continue to bypass stale shared-display behavior where the contract requires it.
- Shared Home quotes may accelerate ordinary/non-fresh requests, but cache age and observation timestamps must prevent rollback.
- Historical close, screener close, lookup time, and current quote remain distinct semantics.

### Detail and compare support
- Slow provider work must not be moved back into Home request paths.
- Default analysis compare/valuation warming is intentional and remains background-only.
- Compare caching and chart caching should be reused rather than creating duplicate provider requests.

### Valuation band
- Valuation-band fetches are expensive and intentionally use:
  - startup background prewarming for default symbols,
  - in-process cache,
  - request coalescing/singleflight,
  - a multi-hour cache lifetime.
- Removing those protections or recomputing the same symbol concurrently is a regression unless deliberately redesigned and benchmarked.

Relevant backend files include:
- `main.py`
- `market_service.py`
- `valuation_band_service.py`
- `realtime_korea.py`

## Performance evidence
Frontend production reference measurements on 2026-10-02 after the coordinated frontend/backend fix, Chromium 390x844, single-run only:
- Samsung Detail visible price ~0.54s
- NVIDIA Detail visible price ~0.95s
- KOSPI index Detail visible price ~1.93s
- valuation band visible ~0.90s
- full heatmap ~0.90s

These are not backend SLAs. Use them as regression clues only with the same measurement harness. Provider/cold-start latency must be separated from code regressions.

## Completion gate
A repeated-problem fix is incomplete unless:
- prior decisions were checked;
- regression/new bug classification is explicit;
- relevant regression tests pass;
- exact production SHA is verified;
- cache/freshness semantics are unchanged unless intentionally redesigned;
- the same request is not recomputed concurrently without justification.
