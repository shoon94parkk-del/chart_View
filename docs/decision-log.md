# Chart View decision log

Append-only record of high-risk behavioral decisions. New work should add entries rather than rewrite history.

## 2026-09-22

### Watchlist add is incremental
**Problem:** adding one stock could feel extremely slow because render/refresh paths reloaded quote and 1-month-return work for the whole watchlist.

**Decision:** persist and paint immediately. The newly added symbol gets a priority `/api/quotes` request, then only that symbol gets a background 1-month `/api/compare` request. Existing watchlist rows are not refetched.

**Protection:** `tests/test_watchlist_recommendation_v55.py`, release-bundle freshness checks, mobile suites.

### Repository memory is part of the engineering system
**Problem:** repeated improvements made through chat can be forgotten and later reverted.

**Decision:** `AGENTS.md`, `docs/project-memory.md`, `docs/regression-guardrails.md`, and this log are durable project memory. Every future behavioral change must consult and update them when relevant.

## 2026-09-21

### Production moved to the new Render service
Current Web production is `chart-view-pkv8`; Toss normally uses this backend. Production/freshness checks must not target legacy `chart-view-bsg6`.

### Safe screener name aliases are allowed
The 2026-09-21 screener completed but publication failed because `010120.KS` appeared as `LS ELECTRIC` in one source and `엘에스일렉트릭` in another. Symbol + code are canonical; safe display-name aliases are accepted, cross-ticker conflicts still fail.

### Screener price is a closing price
The screener previously said `현재가` for a daily close. It now says `기준 종가` and exposes the trade date so realtime quotes elsewhere are not mistaken for inconsistent data.

### Discover is top-first
Entering Discover always selects the base screener, scrolls to the top, shows `#1` first, and keeps a one-tap top control.

### Clean root always starts on Home
Saved history must not reopen TOP PICK or another prior tab on a fresh visit/reload. History restoration is for Back/Forward; explicit deep links remain supported.

### Daily PICK publication is multi-part
Daily PICK is not complete until ranking, performance ledger, deployment, and Home bootstrap freshness all agree. Bootstrap is revalidated rather than allowed to serve a stale prior-day result.

## 2026-09-20

### Chart work must not block Home
Lightweight Charts became lazy, hidden chart calls were guarded, cache TTL/prefetch were bounded, and failed refresh preserves the last chart.

### Home hierarchy is intentional
Home order is Market -> Watchlist -> PICK -> News. Direct-company news is prioritized and separated from industry/indirect items. PICK emphasizes selected names before cumulative stats.

### Home support work is batched/cached
Valuation-band requests were batched, parsed Home source files are memory-cached, and Home watchlist reuses existing quote cache.

## Earlier decisions
See `docs/handover.md`, `docs/app-release-stage12.md`, `docs/data-definitions.md`, and V35-V41 documents for older detailed design/history.
