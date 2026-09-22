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

- U.S. heatmap tile AREA must remain proportional to raw `marketCap`. Korea is the only intentional exception: V61 uses `marketCap^0.58` for mobile readability, and the UI must explicitly label that visual adjustment. Do not add any other non-linear scale silently.
- Small/short heatmap tiles must not render the price line if it would clip; name + daily change take priority.


## Macro / Fed policy
- Do not present monthly `FEDFUNDS` as the current Fed target rate. Current policy display uses daily `DFEDTARL` + `DFEDTARU`; show daily `DFF` separately as EFFR.
- Macro data remains precomputed in `static/data/macro_cache.json`; browser/Render request-time FRED fan-out is forbidden.
- Macro cards with valid `chart_data` must render a visible sparkline without requiring Lightweight Charts.
- Macro traffic-light state must include inflation and Fed stance, but must remain descriptive: never label it as a forecast of the next FOMC action or as a trading recommendation.


## Macro sparkline containment
- Inline macro SVG must declare rendered width/height and stay clipped inside `.mc-mini-chart`; chart paths must never paint into descriptions, neighboring cards, or section headings.
- `.mc-chart-wrapper` and `.mc-mini-chart` keep overflow hidden; ordinary indicator charts are 80px tall and the core net-liquidity chart is explicitly 120px.
- Do not reintroduce negative horizontal margins on macro mini charts.
- Static macro cache shape is 16 rows and includes both `FEDTARGET` and `DFF`.


## Cross-device current quote consistency
- Entering Watchlist may fetch **all saved symbols once through lightweight `/api/quotes`** so every device gets complete today-change coverage. This one-shot bootstrap must never call `/api/compare`.
- Repeated/frequent Watchlist polling remains visibility-scoped; do not turn the 5-second loop into an all-20-symbol historical/current full refresh.
- Every rendered watchlist card keeps a day-change slot even when current quote data is temporarily missing.
- Card and Heatmap on Home must use the freshest shared snapshot. A stale heatmap-only local cache must never override a newer Home snapshot.
- Do not defer the first visible Heatmap sync behind `requestIdleCallback`; desktop busy time must not make Heatmap visibly trail Card.


## Home Card / Heatmap live parity
- Card and Heatmap daily change must come from the same merged Home live-quote rows. If Heatmap applies `QUOTE_CACHE_KEY.dayChange`, Card must be updated in the same render pass.
- `/api/heatmap` is not the intraday quote transport. It may refresh market-cap geometry slowly; live price/day-change uses batch `/api/quotes`.
- Home initial live quote request may cover all displayed Home symbols once (18 <= API max 20). Repeated 5-second polling is limited to the currently open market group and only while Home is active and visible.
- The generic current-quote cache must not impose a 60-second Home lag; current contract is 5 seconds.


## Server-driven Home live cache / private analytics
- Home browser code must not call `/api/quotes` for major Card/Heatmap intraday refreshes. It reads `/api/home-live`, which must be provider-free and memory-only.
- Only the Render background worker may refresh Home major live quotes. It runs at 5-second cadence only when an exchange is open **and** at least one active Home viewer exists.
- Do not let `live_quotes_v56.js` poll Home; it is Watchlist-only after V66.
- Card and Heatmap must continue to apply the exact same shared live rows in one render pass.
- Visitor tracking is anonymous-browser counting only: random local ID -> salted daily hash. Do not collect IP, email, phone, precise location, or account identity for this dashboard.
- `/api/admin/usage` requires `X-ChartView-Admin` with `CHARTVIEW_ADMIN_TOKEN`; never expose the token in HTML/JS/repo.
- Admin usage counts are current-instance memory and may reset on deploy/restart; never present them as durable analytics unless persistent storage is added.

- Automation/Playwright browsers must not contribute to visitor counts; `visitor_v66.js` exits when `navigator.webdriver` is true.
