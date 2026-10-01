# Chart View decision log

Append-only record of high-risk behavioral decisions. New work should add entries rather than rewrite history.

## 2026-09-29 — Home chart load guard

**Observed issue:** The production mobile verification intermittently found a Lightweight Charts script on a fresh Home visit. The old chart tab can briefly retain an active class during route setup, so that class alone is insufficient proof that Analysis is visible.

**Decision:** Chart initialization and data loading now also require the chart tab to be unhidden and the installed bottom navigation to be on Analysis. The standalone legacy chart page, which has no bottom navigation, keeps its prior behavior. A mobile regression check deliberately gives the chart tab a stale active and visible state while Home remains selected, then verifies that no chart library is requested.

**Protection:** `tests/mobile_smoke.cjs`, frontend and boot bundle freshness checks, exact-revision production mobile verification.

The live smoke readiness check now recognizes the single content-addressed boot JavaScript and CSS references. It had continued waiting for four obsolete individual script tags after the boot bundle was introduced.
The same smoke check compares current U.S. prices through `/api/quotes?fresh=true`; `/api/home-live` intentionally serves a saved display value while no Home visitor is active, so using it as a current-price assertion misreported normal idle behavior. The smoke does not create a synthetic visitor in usage analytics.

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

### Daily visitor totals persist in Render Key Value
**Context:** V66 initially counted anonymous daily browsers in process memory, which reset on deploy/restart and made “today” totals unreliable during active development.

**Decision:** persist only the salted daily browser hash set in Render Key Value with a 10-day TTL. Keep live presence (activeNow, activeHome) in process memory because it intentionally expires within the heartbeat window. The admin API reports which backend is active and falls back to memory if Key Value is unavailable.


### Share links preserve the current Chart View context
**Observed issue:** the public share action still hard-coded the retired `chart-view-bsg6` Render URL and always generated a root link, so recipients landed on Home even when the sender was viewing PICK history or a stock detail.

**Decision:** V68 derives the public base from the existing canonical link and serializes only stable routing state into the share URL. AI PICK uses `?tab=screener&view=ai-picks`; stock detail uses the existing detail deep-link contract; other screens preserve their active tab. The receiver remains the existing V3 route/deep-link implementation.

**Rollback:** `backup/pre-context-share-v68-20260923`.

## 2026-09-27 — 홈/전체 히트맵 시세 소스 통일
미국 전체 히트맵의 legacy heatmap.json이 2025-12-23 가격/등락률을 포함해 현재 홈 시세와 충돌하는 문제가 확인됐다. legacy 파일은 종목 목록/시총 weight만 유지하고 시세 필드는 무시한다. 전체 히트맵은 한국/미국 모두 canonical fetch_quote_snapshot 경로로 60종목을 백그라운드 갱신하며, Home과 중복되는 18종목은 실제 Home UI가 읽는 HOME_SNAPSHOT_CACHE를 최종 오버레이한다.

### Home live reads are non-blocking cache reads
**Context:** Apps in Toss now reads the shared Home snapshot roughly every 10 seconds while visible. The old cold-start fallback awaited provider refresh inside `/api/home-live`, allowing a user cache read to become provider work.

**Decision:** `/api/home-live` is a pure shared-memory read. If the cache is not warmed it only wakes the existing activity-gated worker; startup/worker code owns provider refresh. The response is no-store so freshness is controlled by Render memory rather than intermediary browser caching.

## 2026-09-28 — foreground API와 background market refresh를 격리
실서비스 성능 감사에서 차트 7.1초, 관심종목 4.2초, 컨센서스 3.9초, 밴드 3.8초 등 첫 요청 지연이 확인됐다. 동시에 startup/Home/full-heatmap refresh가 수십 개 `asyncio.to_thread` 작업을 기본 executor에 넣고 있어 foreground provider 호출과 경쟁할 수 있었다. 배경 시세 갱신은 6-thread 전용 executor로 분리하고, heartbeat Redis write는 비동기 후처리한다. 관심종목 시세는 Home 공용 캐시를 우선 재사용한다.

## 2026-09-28 — 기본 차트/밸류에이션을 서버에서 미리 warm
1차 성능 격리 후 홈·관심·컨센서스·밴드는 1초 아래로 내려왔지만 기본 차트 cold 4.35초, valuation cold 2.84초가 남았다. Toss 기본 선택 3종목의 1mo compare/valuation을 서버 시작 시 background executor에서 미리 warm하고 compare TTL을 300초로 확장한다. 사용자별 prefetch로 provider 호출을 늘리지 않고 서버 1회 warm 결과를 모든 사용자와 공유한다.


## 2026-09-28 — P0 compare stale-while-revalidate
실서비스 감사에서 기본 차트는 prewarm 직후 빠르지만 5분 TTL이 지난 첫 요청이 Yahoo Chart provider를 직접 기다리며 약 4초까지 느려졌다. `fetch_compare_stock()`은 마지막 정상 차트를 즉시 반환하고, 300초 이상 지난 값은 전용 2-thread refresh executor에서 갱신한다. provider 실패는 정상 캐시를 덮어쓰지 않으며, 최초 실패만 30초 negative cache한다. 이 구조의 목표는 정규장/장외의 Home polling 부하와 무관하게 이미 조회된 차트의 사용자 경로를 provider I/O에서 분리하는 것이다.


## 2026-09-28 — P0 compare cache hit request fast path
Production audit after SWR deployment still measured /api/compare at about 4.1s even though startup prewarm succeeded. The endpoint was sending every ticker, including memory-cache hits, through asyncio.to_thread and the shared foreground executor. /api/compare now peeks the in-memory SWR cache synchronously and sends only true misses to worker threads. Response diagnostics expose cacheHits and providerFetches.

## 2026-09-28 — P0 startup provider priority
Production audit exposed a 7s Home cold load with /api/market-now at 6.6s. Startup was launching market-now, default analysis, Home live, Home snapshot, and full heatmap refreshes together on the same provider/background capacity. Critical first-user caches now warm in a bounded sequence (market-now, then default chart/valuation) before bulk Home/full-heatmap refresh jobs start. Render keeps the previous revision live during startup, so deploy latency is preferred over first-user latency.


## 2026-09-28 — P0 remove deploy-time provider herd
Production logs showed the legacy 5-minute snapshot warmer forcing /api/market-now?fresh=1 and /api/home-snapshot?fresh=1; the Home snapshot force refresh took 11.1s. At the same time startup launched Home live, Home snapshot, and full heatmap refreshes. Even cache-only /api/compare requests then waited several seconds. The package no longer auto-starts the self-request warmer, startup no longer launches bulk provider refreshes, and fetch_quote_snapshot is singleflight-coalesced so overlapping demand-driven refreshes for the same ticker share one provider call.


## 2026-09-28 — P0 response-first stale refresh
A live audit after removing the deploy-time warmer improved Home to 1.67s, but a cache-only compare request still took 2.30s. Render request logs showed the first Home navigation immediately scheduling stale market-now and Home snapshot provider refreshes; those background jobs began before cached HTTP responses had fully drained. Stale market-now refresh is now delayed 3s, Home snapshot refresh 6s, and the first active Home session gets a 5s live-quote grace. Latency-sensitive background work is capped at 2 threads, while large Home snapshot/full-heatmap refreshes are serialized on a separate 1-thread bulk executor.


## 2026-09-28 — P0 valuation stale-while-revalidate
The corrected production audit measured valuation Cold at 4.65s while SPA re-entry was 91ms. The default valuation cache used a hard 300s TTL, so startup prewarm expired and the first user after five minutes paid Yahoo Chart/Fundamentals latency. Valuation now returns the last successful memory value immediately, refreshes stale entries on a dedicated single-worker executor, and /api/valuation bypasses the shared worker queue for cache hits. Response diagnostics expose cacheHits and providerFetches.


## 2026-09-28 — Original Chart View Home first-paint P0
Fresh Chromium measurement of the original Chart View showed Home at ~1.5–2.7s while internal screens were usually ~0.05–0.2s. First paint was competing with non-critical Home work: duplicate AI bootstrap on initial pageshow, profile-sync status, DATA STATUS macro lookup, and immediate heatmap geometry refresh. These tasks are now deferred until idle/after first paint. Home snapshot and heatmap share the v18 local cache so geometry can render from the Home snapshot before a background refresh.


## 2026-09-28 — Original Home first-paint P0 v2
Regular-market Chromium re-audit after P0 v1 still showed Home median 2.14s with a 4.63s outlier. requestIdleCallback was not a reliable first-paint boundary because it could fire while critical network work was still pending. Hidden Watchlist rendering also triggered /api/quotes before the user opened Watchlist. V2 replaces idle scheduling with explicit first-paint grace periods, delays below-fold news, initializes profile sync on Watchlist entry (8s fallback), and suppresses hidden Watchlist quote refresh until the tab is visible.


## 2026-09-28 — Original Chart View single boot bundle
Regular-market Chromium runs still showed Home at 1.86–4.63s even after deferring non-critical Home API work. Render CPU remained low, while the original page requested 17 JavaScript files at startup plus a 31-script release bundle. The initial browser path is therefore consolidated into one content-addressed chartview_boot_bundle.js request. The boot generator preserves the legacy execution semantics (the former non-defer p2 revisit script first, then the former defer sequence), while hidden version sentinels keep the existing release-bundle and AI-widget freshness verifier compatible.


## 2026-09-28 — Original boot CSS bundle P0
Regular-market Chromium resource timing showed a 9.68s Home outlier even after the single JavaScript boot bundle. During that run the JS boot bundle took ~7.0s and the release CSS bundle ~6.6s while Render CPU remained near idle, indicating startup request/transfer tail latency rather than server compute saturation. The eight initial stylesheet requests are therefore consolidated into one content-addressed chartview_boot_bundle.css. home_summary_v54 is moved into the JS boot bundle, and promo/ui-continuity loaders explicitly avoid re-requesting helpers already embedded in the boot bundle.

## 2026-09-28 — Separate published PICK history from post-publication sell monitoring
Decision: keep `ai_daily_rankings.json` immutable as the publication record and add a separate PICK monitor ledger/history. Legacy picks are seeded from their published reason only. Monitoring uses `PENDING_REVIEW/KEEP/WATCH/SELL_REVIEW/EXIT`, with automatic exit prohibited and technical/price weakness insufficient on its own for a sell-review state. This separation prevents later monitoring from rewriting what was actually recommended at the time.

## 2026-09-28 — P1 PICK review is evidence-driven and visible beside the existing ledger
Decision: add a deterministic review layer between web research and the persistent PICK monitor. Research writes verified, dated evidence; code derives KEEP/WATCH/SELL_REVIEW using fixed rules. Evidence older than the PICK cannot change the state, price/technical weakness alone is excluded, and EXIT remains a user action. The web UI exposes this as a separate PICK 점검 view within the existing AI PICK discovery shell so performance history and thesis monitoring stay conceptually separate.



## 2026-09-28 — P0 live quote freshness
- Korean stocks continue to use the existing Naver/KRX/Koscom realtime path.
- Yahoo-backed U.S. stocks and cash indices now prefer chart metadata `regularMarketPrice` + `regularMarketTime` from the same provider response instead of treating the last closed 5-minute bar as the current quote.
- The 5-minute bar remains only a fallback when current quote metadata is absent.
- Market-now SWR freshness is tightened from 60s to 12s with a 5s refresh guard; refresh remains response-first/background so Home navigation does not wait on provider I/O.


## 2026-09-28 — Canonical live quote parity across Home and detail
The detail screen may explicitly request `/api/quotes?fresh=true`. Fresh mode bypasses the shared Home snapshot so navigation cannot regress to an older Home-cache timestamp; it calls the canonical provider path instead (Naver/KRX/Koscom for Korean equities via realtime_korea, Yahoo regularMarketPrice-first for U.S. symbols). Normal Home/watchlist requests keep the shared-cache fast path.

## 2026-09-28 — Shared quote freshness is ticker-scoped
A production screenshot showed Samsung Electronics and SK hynix frozen at 13:37 while non-major Korean watchlist rows were current at 18:23. The shared Home cache had market-level freshness: another successful Korean refresh could make stale major-stock rows look reusable. Cache eligibility is now ticker-scoped, provider fallback repairs the shared row, stale disk seeds do not advance freshness, and the Korean live window covers NXT through 20:00 KST.


## 2026-09-29 — Popular screener technical signals
The daily Korean screener now downloads one year of daily history and publishes explicit fields used by the Toss one-tap popular filters: MACD bullish/cross-up, 20/60 golden cross, price>20MA>60MA trend, 52-week high distance/near-high, and Bollinger upper breakout. These are deterministic end-of-day technical observations, not recommendation labels. Existing RSI, volume ratio, returns, moving averages and technical score remain unchanged.

## 2026-09-29 — DART receipt-aware cache for repeat stock views
The major-company static cache was discarded after 14 days even when its daily workflow found no new annual report. Keep validated static rows until replaced. Store other successfully parsed Korean stock reports in the existing Render Key Value, keyed by stock code, receipt number, and successful check time. Return a cached report before checking DART; after 24 hours, compare the latest receipt in a background worker and parse the viewer only when the receipt changes. Provider and parser failures preserve the last validated report. The free Key Value service has persistence disabled, so it is a best-effort shared cache; checked-in major-company rows remain the durable fallback.
## 2026-09-29 — Toss share previews
The Toss static client cannot provide stock-specific Open Graph metadata from a hash route. Add a read-only `/share/toss/{tab}` backend landing page with server-rendered title, description, logo image, and redirect into the matching Toss route. Detail cards resolve the name from the local stock universe rather than trusting an editable URL name. The preview image is a stable branded PNG without live prices, so shared cards never imply stale market data.

## 2026-09-29 — DART sales table coverage for Hanwha Ocean and Dongseong Finetec
The latest `[첨부정정]사업보고서` for Dongseong Finetec contained only an audit attachment. OpenDART's latest-only list must fall back to the full public DART business-report search rather than selecting an older annual report. Hanwha Ocean discloses segment sales under current-period columns with domestic/export rows and a named consolidation adjustment. Parse that shape only when segment amounts plus adjustment reconcile with the reported total within 1%; never infer a mix from a product description table. Precompute both validated 2025 reports into the static DART context, alongside the existing receipt-aware cache. Both OpenDART-listed and public DART viewer results are official-source cache inputs. The Toss revenue card labels the consolidation adjustment so shares over 100% in aggregate are interpretable.
Normalize only DART's spaced `사 업 부 문` and `가 스` cell labels for readable segment names; keep the reported amounts and shares intact.
For the same receipt number, prefer the newly built validated static row over an older Redis row so parser corrections appear immediately after deploy.
## 2026-09-29 — OpenDART 재무 흐름 API

한국 종목 상세의 매출액·영업이익 추이는 `/api/financial-history`에서 OpenDART 단일회사 전체 재무제표를 조회한다. 동일 사업보고서의 당기·전기·전전기 손익계산서 값을 최대 3개 연도로 묶고, 최근 분기·반기는 당기/전기 **누적** 금액만 비교한다. 연결(CFS)을 우선하고 없으면 별도(OFS)를 명시해 사용하며 서로 다른 기준을 혼합하지 않는다. 계정이 중복·누락되거나 접수번호/통화가 맞지 않으면 수치를 표시하지 않는다. 결과는 메모리·Render Key Value에 저장하고 하루마다 뒤에서 재확인한다. 제공처 실패가 기존 검증값을 지우지 않도록 한다.

2026-09-29 후속: 무료 Key Value가 비워진 재시작 직후에도 주요 종목 상세가 느려지지 않도록 공식 DART 원문으로 검증한 14개 회사의 연간·반기 재무 결과를 `static/data/dart_financial_history.json`에 미리 저장한다. 이 파일을 먼저 보여주고 API 최신성 확인은 뒤에서 한다. 기존 DART 사업 맥락 GitHub Actions가 하루 한 번 재무 파일도 갱신하되, 공시값에 변화가 없으면 커밋하지 않는다.
## 2026-09-29 — 뉴스 기반 직접 거래 단서 판정 강화

종목 상세와 IDEA LAB의 직접 관계 API는 여러 종목을 나열한 특징주·장마감·기업 공시 기사에서 계약 단어만 발견해 관계를 만들지 않는다. 단일 기업 기사에서 두 상장사와 구체적 계약·납품 표현이 같은 문맥에 있는 경우로 제한한다. 수주잔고·막연한 고객사 확대는 관계 근거로 쓰지 않는다. 이닉스/SK하이닉스, HD현대/HD현대중공업처럼 회사명이 다른 회사명 안에 포함된 경우 짧은 이름을 별도 거래상대로 인식하지 않는다. 근거가 부족하면 관계를 표시하지 않는다.

운영 검증에서 별도 검색어 4개를 순차 조회하는 첫 요청이 토스의 관계 근거 표시 제한시간을 넘었다. 관계 API는 이미 수집한 해당 종목 뉴스만 판정하고 9초 안에 자료 없음/제공처 지연을 반환한다. 오래된 계약 기사의 누락보다 오탐과 상세 화면 지연을 줄이는 쪽을 우선한다.

## 2026-10-01 — DART financial quality and conservative review facts
The financial-history API adds schemaVersion 2 and optional quality accounts (net income, operating cash flow, inventories, receivables, assets, liabilities, equity), with account ID/name/statement/receipt provenance. Revenue/profit fields remain compatible. IS/CIS interim values require cumulative add_amount; CF cumulative values use cash-flow amount fields; BS balances compare with previous year end. Missing, duplicate, mismatched receipt/currency accounts remain null. No industry-independent investment score or forecast is produced.
Redis uses a v2 namespace. Partial refreshes and the daily generator retain older validated periods with their original quality/source data when basis and currency match; no CFS/OFS mixing. Major-stock static data is upgraded by the existing secret-backed workflow, without adding requests per company.
