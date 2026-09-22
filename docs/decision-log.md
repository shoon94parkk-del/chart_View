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
