# Chart View regression guardrails

Last updated: 2026-09-22

These rules come from bugs already seen in production. Do not remove a guardrail merely to make a test pass.

## Navigation / startup
- Clean root -> Home.
- Explicit deep links still work.
- Back/Forward restoration does not become clean-root behavior.
- Home does not load Lightweight Charts.
- Hidden chart code does not call `loadData()`.
- Failed chart refresh preserves the last valid chart.

## Watchlist responsiveness
- Add/remove feels immediate and does not wait for network.
- Adding one stock does not refetch the full watchlist.
- Merely opening Watchlist does not trigger a foreground/full-list historical refresh.
- App boot may quietly refresh current quotes but does not start full quote + 1-month historical refresh work.
- Cached rows paint first on entry.
- Entry-time revalidation may refresh stale current quotes quietly, but 1-month returns use a separate long TTL and deferred background refresh.
- Explicit manual refresh is the only foreground path that may force quote + return refresh for the whole list.
- New stock gets `/api/quotes` first.
- Only the new stock gets its 1-month `/api/compare` fetch.
- Existing cached rows remain visible if refresh fails.
- Existing localStorage contracts remain compatible.
- Live polling must never call `/api/compare`; it may update current-price fields only through `/api/quotes`.
- Frequent Korean quote polling runs only while Watchlist is active/visible; hidden/inactive screens must not keep polling.
- Home live quote refresh must not duplicate the existing cache-first boot refresh.
- Live quote cache merges must preserve the cached 1-month return and its independent freshness timestamp.
- Korean current prices must keep using the unified Naver Finance/KRX-Koscom path across Home, Watchlist, compare, and valuation.

## Screener trust
- Discover opens base screener and starts at top.
- First visible rank is `#1`.
- `맨 위로` remains available.
- Screener price label is `기준 종가`, never `현재가`.
- Trade date is explicit.
- Freshness verifies `chart-view-pkv8`.
- Same-symbol display-name aliases cannot block publication.
- A name that belongs to another symbol still blocks publication.

## Daily PICK freshness
- Ranking and performance ledger agree on selected date/names.
- New daily PICK is not hidden by stale HTTP cache.
- `오늘 선정` is used only for current KST date.

## Production / release integrity
- Current Web production is `https://chart-view-pkv8.onrender.com`.
- Old `chart-view-bsg6` is not a production verification target.
- Source, generated bundle, and asset hash stay synchronized.
- `python scripts/build_frontend_bundle.py --check` passes.
- Exact tested SHA must equal deployed Render revision.
- Render status `live` alone is insufficient.

## Adopted P1 UX
- Home order remains Market -> Watchlist -> PICK -> News unless intentionally redesigned.
- Direct company news precedes indirect/industry news.
- Home-only modules do not leak into other tabs.
- PICK selected names remain more prominent than cumulative statistics.
- Watchlist explicitly communicates the 1-month return period.
- Basis/date metadata must remain readable on mobile.

## If an intentional redesign changes a guardrail
Update implementation, regression test, this document, and `docs/decision-log.md` together, then verify exact production revision.

## Home heatmap
- Heatmap must not add blocking work to initial Home paint; network refresh starts only after Home/cache content is available and the browser is idle.
- `/api/heatmap` reuses the shared Home SWR snapshot and must not directly fan out to quote providers.
- Korean and U.S. market caps are sized within separate groups; never compare raw KRW market cap directly with raw USD market cap.
- Snapshot `marketCap` must be actual market capitalization from valuation data, never trading volume.
- Existing major-stock card view remains available through the Card/Heatmap toggle and is the rollback fallback.

- Home SWR quote refresh must never overwrite a previously valid heatmap marketCap with 0/null when a live quote provider omits market capitalization.
- Heatmap logos must participate in tile layout (inline with the name), not float with absolute positioning over text.
- Card-only previous/next strip controls stay hidden while Heatmap view is active.
- A market with temporarily missing cap data shows a clear refresh state; never render a large unexplained blank rectangle.
