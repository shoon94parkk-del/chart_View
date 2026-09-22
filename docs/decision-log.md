# Chart View decision log

Append-only record of high-risk behavioral decisions. New work should add entries rather than rewrite history.

## 2026-09-22

### Live quotes are visible-surface polling only
**Problem:** OpenStock-style frequent price updates improve legibility, but naive polling can recreate the old watchlist full-refresh latency, duplicate Home boot work, or accidentally refresh 1-month history every few seconds.

**Decision:** keep Chart View's existing providers and data contracts. Korean current prices remain on the unified Naver Finance/KRX-Koscom path; global quotes remain on the existing Yahoo quote path. The additive `live_quotes_v56.js` layer refreshes only `/api/quotes`, never `/api/compare`: visible Watchlist Korean rows may update every 5 seconds while the market is open, closed-market/global rows use a slower 30-second cadence, and Home uses a 30-second cadence. Polling stops when the document is hidden or the user leaves Home/Watchlist. Cached 1-month returns are preserved.

**Protection:** `tests/live_quotes_v56_contract.cjs`, existing Korean price-consistency tests, watchlist cache/incremental-refresh tests, mobile suites. Rollback baseline: branch `backup/pre-openstock-ux-20260922` at `71d78dcb22fed5ac4826c6567ae7039221360215`.


### Watchlist entry is stale-while-revalidate, not full refresh
**Problem:** even after incremental add was fixed, app boot/watchlist entry could still start a full quote + 1-month-return refresh for every saved stock, so simply opening the screen felt slow.

**Decision:** Watchlist entry paints local cached values immediately. App boot may quietly revalidate only lightweight current quotes, but never starts 1-month historical refreshes. Entry may also revalidate stale current quotes without blocking, while 1-month returns use a separate 12-hour freshness window and are deferred until idle. Only the explicit refresh button may force a foreground full-list quote + return refresh.

**Protection:** `tests/test_watchlist_recommendation_v55.py`, generated-bundle freshness check, mobile regression suites.


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

### Home major stocks get a cache-backed market-cap heatmap
**Problem:** The horizontal major-stock strip is easy to read one-by-one but does not communicate market breadth or relative company scale like Finviz. A naive heatmap implementation would add many provider calls and slow Home.

**Decision:** add an independent V57 heatmap layer with a Card/Heatmap toggle. It reuses the existing Home stale-while-revalidate snapshot via a cheap `/api/heatmap` projection. The browser requests it only after idle and then at 60-second visible-Home intervals. Korea and U.S. are rendered as separate treemap groups because their raw market caps are denominated in different currencies. Actual market cap comes from the valuation cache; the previous snapshot generator bug that wrote trading volume into `marketCap` is removed. Logos render only on sufficiently large tiles.

**Protection:** `tests/home_heatmap_v57_contract.cjs`, existing Home/mobile suites, exact-revision production verification. Rollback baseline: `backup/pre-home-heatmap-20260922` at `7be471906681700b0509e6186a734d385b636c9c`.

### Heatmap mobile rendering is content-first, not decorative
**Observed issue:** The first V57 mobile render exposed two defects: Korean live refreshes omitted market cap and replaced valid cached cap with zero, producing an empty Korea board; large absolute-positioned logo chips overlapped text and card-only arrow controls remained visible.

**Decision:** preserve the last valid market cap through Home SWR, invalidate the first heatmap browser cache with V58, place logos inline beside company names only on genuinely large tiles, suppress prices in constrained tiles, hide card-strip arrows in Heatmap mode, and render an explicit loading state when a market temporarily has no cap rows. The underlying Card view and data provider contracts remain unchanged.

**Rollback:** `backup/pre-heatmap-mobile-fix-20260922` at `555d7134eb52b2ae535bdb4ecb22115d5518962d`.

### Heatmap area means actual market-cap share
**Observed issue:** V57/V58 used `marketCap^0.58` to keep small tiles readable. That made NVIDIA, the largest U.S. company in the current dataset, look only marginally larger than much smaller companies and made the visual less faithful to Finviz-style market-cap maps.

**Decision:** V59 uses raw market capitalization as the treemap weight inside each market group. Therefore a tile's area directly represents that stock's share of the displayed companies' total market cap. Korea and U.S. remain separate currency groups. Text readability is handled by hiding secondary price text in constrained tiles, not by distorting market-cap area.

**Rollback:** `backup/pre-true-cap-heatmap-20260922` at `261b106334a5b1e7bb6d17cb283a337b33cb5d64`.

### Korea heatmap gets a labeled mild cap compression; U.S. stays true-cap
**Observed issue:** After V59 switched both markets to raw market-cap area, the small Korea representative set became dominated by Samsung Electronics and SK hynix, leaving the remaining Korean large-cap tiles too small to read on mobile. The U.S. V59 layout was accepted and should not change.

**Decision:** V60 keeps U.S. treemap weight as raw `marketCap`, while Korea alone uses `marketCap^0.82`. This is deliberately mild—less distortion than the original V57/V58 `^0.58`—and the UI explicitly says the Korean map is visually adjusted while the U.S. map uses actual market-cap share. Data values themselves remain real market-cap values; only Korean tile geometry is compressed.

**Rollback:** `backup/pre-kr-heatmap-compression-v60-20260922` at `b50eee65a09691d77a225420977654dd5bfc0c29`.

### Korea heatmap returns to the stronger first-layout compression
**Observed issue:** V60's Korea-only `marketCap^0.82` adjustment was too mild; Samsung Electronics and SK hynix still occupied nearly the same dominant geometry as raw market-cap mode, unlike the initially preferred balanced Korean layout.

**Decision:** V61 keeps U.S. unchanged on raw `marketCap`, but Korea uses `marketCap^0.58`, matching the geometry philosophy of the first accepted Korean heatmap. The UI continues to label Korea as visually adjusted. Underlying market-cap values and quote values remain unchanged.

**Rollback:** `backup/pre-kr-heatmap-v61-20260922` at `31ee4ad260c93b7c722199e0f0acef80722f32ac`.


### Macro policy rate uses daily target bounds and EFFR
**Observed issue:** The Market macro summary showed 3.6% as “Fed Rate” because it used monthly-average FRED `FEDFUNDS`. After an FOMC target change, that monthly series can remain stale for the user-facing meaning of “current policy rate”. Macro cards also had numeric values but blank mini-chart areas because their renderer depended on Lightweight Charts, which is intentionally lazy-loaded only for Analysis.

**Decision:** V62 replaces displayed `FEDFUNDS` with a synthetic `FEDTARGET` row built from official daily FRED target lower/upper bounds (`DFEDTARL`, `DFEDTARU`) and adds daily `DFF` as EFFR. All collection stays in the scheduled GitHub Action and the app still serves a committed cache. Macro charts use inline SVG sparklines from cached chart data, adding no external chart-library request. The traffic light is reworked around inflation, Fed stance/recent target move, labor/activity, credit/VIX and liquidity, as a descriptive regime state only.

**Protection:** `tests/test_macro_pce.py`, `tests/macro_policy_v62_contract.cjs`, normal mobile/production suites. Rollback: `backup/pre-macro-fed-signal-v62-20260922`.


### Macro daily Fed series use the stable FRED mirror in cache generation
**Observed issue:** the first V62 main cache run timed out on direct FRED CSV for both `DFF` and the target-range bounds, while all Equibles-mirrored FRED series completed normally.

**Decision:** V62b uses Equibles CSV for `DFF`, `DFEDTARL`, and `DFEDTARU` during the scheduled GitHub cache build. The series remain Federal Reserve/FRED-defined and link to FRED; only the transport path changes. Runtime remains cache-only.


### Macro sparklines are sized by CSS, not SVG intrinsic dimensions
**Observed issue:** V62 restored macro charts with inline SVG, but the SVG specified only a viewBox. On Samsung Internet/mobile the SVG intrinsic size overflowed the 80px chart slot, so the path painted through descriptions and subsequent cards.

**Decision:** V63 sets SVG width/height to 100%, clips wrapper and chart container, removes negative chart margins, and explicitly sizes the core chart to 120px. No data or macro-regime semantics change. App CI also fixes the expected macro cache shape at 16 rows including `FEDTARGET` and `DFF`.

**Rollback:** `backup/pre-macro-chart-clip-v63-20260922` at `d67da7986c51c67abd252b4cddabb52cb7955f37`.


### Watchlist bootstrap is all-symbol once; Heatmap follows the freshest Home snapshot
**Observed issue:** Desktop and mobile showed different Watchlist “today” coverage because V56 polled only cards currently inside the viewport. A large desktop viewport populated more symbols, while mobile left off-screen rows without `dayChange`. Separately, Home Card updated from a fresh `/api/home-snapshot`, but Heatmap preferred its older private local cache and waited for an idle callback before revalidating, making desktop Heatmap visibly lag.

**Decision:** V64 performs one lightweight all-symbol current-quote bootstrap whenever Watchlist becomes active, then returns to the existing visibility-scoped polling cadence. Historical 1-month returns remain separate and are never fetched by this path. Heatmap selects the freshest payload between the shared Home snapshot and its private cache, prefers Home on equal timestamps, and schedules first revalidation promptly rather than waiting for browser idle.

**Rollback:** `backup/pre-cross-device-sync-v64-20260922` at `d52f21c34557f0528a5ecc9300d20e4df0314d52`.


### Manual PICK corrections may leave fewer than three names
**Context:** Intekplus was manually selected again on 2026-09-17 and 2026-09-21 even though its valid first PICK was 2026-09-14. The user asked to remove the later duplicate selections, not substitute other stocks.

**Decision:** remove only those later Intekplus entries from the ranking ledger and performance ledger. Manual `user_final_selection` days are valid with 1–3 consecutively ranked picks; GPT-reviewed automated TOP3 days still require exactly three. Never invent a replacement when correcting historical manual selections.


### Home intraday freshness is quote-batch driven, not heatmap-endpoint driven
**Observed issue:** V64 synchronized cache preference, but Heatmap still overlaid `chartview-watchlist-quotes-v33.dayChange` while the Card retained the Home snapshot value. Heatmap could therefore show a newer percentage than Card. The separate `/api/heatmap` revalidation was also slower than the small-card path.

**Decision:** V65 separates slow geometry from fast quote state. Market-cap geometry remains cached and uses `/api/heatmap` only on a 5-minute cadence. One concurrent batch `/api/quotes` request fetches all 18 displayed symbols on Home activation; while a market is open, only that market's displayed symbols are refreshed every 5 seconds. The same merged rows update Card and Heatmap in one render pass. The server current-quote TTL is reduced from 60s to 5s. No extra historical calls are introduced.

**Rollback:** `backup/pre-home-card-heatmap-parity-v65-20260922`.


### Home live quotes become server-driven and activity-gated
**Context:** V65 made Card and Heatmap share one fast quote batch, but each browser still triggered `/api/quotes`. On the Free Render plan this meant user traffic could still initiate provider work, while the desired model was “Render owns the latest snapshot; users only read it”.

**Decision:** V66 introduces one Render background worker. It refreshes the currently open market's Home symbols every 5 seconds only while a visitor heartbeat says at least one user is actively viewing Home. When Home has no active viewers, provider polling stops; when markets are closed, it also stops. Browsers poll only the tiny in-memory `/api/home-live` payload. This caps provider work independent of concurrent Home viewers while preserving Card/Heatmap parity.

### Usage counting is private, anonymous, and process-local
**Decision:** add a random browser heartbeat and store only salted daily hashes in Render memory. The private `/admin/usage` page uses a server environment token and is not linked from the public UI. Counts are intentionally labeled as current-instance values because free durable analytics storage is not part of V66.


### Home today change is one-session change, not Yahoo chart-range return
**Observed issue:** the persistent Home snapshot requested Yahoo range=5d and calculated change from meta.previousClose/chartPreviousClose. On 2026-09-22 this produced values such as NVDA +7.78%, exactly Yahoo's 5D return, while the UI labeled the figure as today's change.

**Decision:** V67 computes U.S. snapshot change from the last two valid daily closes, uses Naver fluctuationsRatio for Korean snapshot rows, and wires the existing Naver realtime patch into the actual functions imported by main.py. Geometry/market-cap caching is unchanged.

**Rollback:** backup/pre-daily-change-fix-v67-20260922.
