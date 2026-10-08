# Chart View decision log

## 2026-10-05 — Verify collection throughput before retaining an optimization

**Classification:** New behavior, follow-up to the separate guru screening collector. The initial sequential run collected 91 companies within its time budget. Two workers then collected 900 companies / 5,942 requests. A trial of official multiple-company period prefetch collected only 18 companies / 100 requests in 20 minutes, so PR126 removed that prefetch and restored receipt-matched individual annual-period validation. Removing the unused fiscal-month profile request remains valid: it never established an annual observation period.

**Protection:** Two thread-local sessions share locked request/deadline/020 budgets; missing histories precede oldest due rechecks. Collection overlap, budget stop, provider failure, authoritative annual periods and no upfront bulk delay have regression tests. The resumed individual-period run collected 1,049 companies / 6,500 requests without provider errors. This is observed throughput, not a provider latency guarantee.

**Deployment limitation:** GitHub updates did not produce Render deployments despite the auto-deploy setting, and the existing deployment hook secret is absent. The current release is manually deployed and verified against the exact tested main revision. Scheduled collection is configured; scheduled evidence publication to the running backend still needs the existing Render account connection repaired. Do not claim end-to-end daily deployment from a successful collection job alone.

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

2026-10-01 live-data follow-up: prior interim CF uses frmtrm_q_amount (DART documentation's 3-month caveat applies to IS/CIS only), before considering frmtrm_amount. Preserve the reported current/prior/interim period labels in account provenance. Parser version 3 wins against version 2 at identical receipts; CurrentTradeReceivables is preferred to combined other receivables.

## 2026-10-01 DART revenue denominator metadata
Business-report adds optional revenueBasis (denominator, totalAmount, positiveSegmentTotal, signed adjustmentAmount, reconciled). Existing items, shares and report/source fields remain compatible. Reconciliation tolerance is 1% of disclosed total; absent component metadata is not verified. The Samsung general table now returns its existing consolidation flag and amount, matching the Hanwha period table. Samsung and Hanwha static rows were reread from official DART source and carry verified metadata for immediate cold-start display. The separate web UI is unchanged. Validation: 45 DART business/financial/cache tests plus scripts/build_frontend_bundle.py --check.

## 2026-10-01 Live QA follow-up: co-supplier relationship false positive
Production Samsung detail showed SK hynix as a direct contract counterparty based on a Broadcom/Anthropic article listing several memory suppliers. Name proximity plus a contract word in a flattened summary was insufficient. Require explicit named actor and named contract-target particles in either direction when both issuers occur in the evidence; co-supplier lists and peer comparison wording do not establish a pair. Keep established dedicated-subject customer-list fixtures valid. Ambiguous syntax is omitted rather than promoted to a direct relationship. No extra provider requests, endpoints or news fetches were added.
Regression reproduced two false positives before the fix. DART business/financial/cache plus relationship tests: 63 passed. Separate web bundle check is unchanged. Runtime deployment resets the in-process six-hour relationship cache.

## 2026-10-02 · 독립 분기 공시 캐시
- /api/financial-quarters 추가. 기존 금융/비교 API와 별개로 bounded background workers에서 공시를 수집하며 cache-first + stale refresh를 제공한다.
- interim parser에 singleQuarter(3개월 IS 값) 필드를 추가하고 기존 누적 계약을 유지한다. Q4는 연간−Q3 누적, 동일 basis/currency에서만 계산한다. 누락값은 None, TTM은 최신 연속 네 분기에 한정한다.
- 메모리/Redis/checked-in static quarter cache 재사용. established company set의 일일 DART workflow가 quarterly cache도 생성한다. 계산값은 양쪽 원문 연결.
- 조회 성공/실패 수를 보존하며 전부 실패 시 기존 성공 checkedAt을 새 시각으로 바꾸지 않는다. 부분 실패는 별도 표시한다. 사용자 재시도는 refresh=true로 singleflight 재확인하며 polling은 force하지 않는다.
- 관련 pytest와 generated frontend bundle check를 통과시킨 정확한 main만 기존 Render 서비스로 배포한다.

## 2026-10-02 Sector heatmap metadata
Full heatmap keeps its 20 KR / 40 US quote budget. US layout metadata supplies classification and market-cap weights only; the 40-company universe includes the largest company of every available sector before filling by cap. KR rows carry KRX industry/products from the existing local screener. No legacy price/change is promoted to a quote. Static metadata enrichment adds no provider requests; canonical quote/date/stale fields remain authoritative. Tests: test_heatmap_metadata plus existing performance isolation/home snapshot contracts, generated Web bundle check. Toss sector aggregates exclude missing/stale/unclassified/different-session rows and disclose covered universe, not official sector indexes.

## 2026-10-02 Final loading audit follow-up
- Full heatmap provider snapshots are shared for five minutes. Home canonical quote overlays keep their existing short polling cadence.
- Partial or failed full snapshots wait at least 60 seconds before automatic provider retries; a three-second UI poll must not fan out a new 60-company batch. Explicit fresh requests still bypass the cooldown. Original observed dates and partial coverage remain visible.
- Render CPU usage reached the 0.15 CPU allocation during slow live QA. This does not prove a single cause, but the unbounded incomplete-cache restart path was independently identified and removed.
- Validation: 36 heatmap/cache/performance/app regression tests and generated Web bundle check.

Final review follow-up: complete coverage containing retained stale provider rows uses the 60-second retry policy, including both internal refresh guards. Added a warm full-cache test that asserts the provider is actually called after the cooldown.

Cold-start live QA found the full 60-company background batch could exceed the frontend polling window. Fetch one company per US sector first and publish successful dated quote rows incrementally before the batch finishes. Provider count and one-worker budget are unchanged; partial coverage remains labeled incomplete and quoted rows preserve observation dates. Regression asserts partial cache publication while refresh is still running.


## 2026-10-02 — 이미 해결된 성능/캐시 문제의 재구현 금지

**관찰된 문제:** 홈/상세 시세, 캐시, valuation 계열 성능처럼 과거에 이미 개선된 영역이 후속 변경에서 다시 느려지거나 깨졌고, 이를 새 문제처럼 다시 최적화하는 작업이 반복됐다.

**결정:** 백엔드 성능·시세·캐시·provider routing 변경 전에는 `docs/no-repeat-regression-policy.md`를 반드시 확인하고, 새 기능/새 버그/기존 수정의 회귀 중 하나로 먼저 분류한다. 회귀라면 기존 known-good 계약을 복원하는 것이 우선이며, 두 번째 경쟁 캐시나 provider 경로를 새로 만들지 않는다.

**보호:** `AGENTS.md`가 no-repeat 정책을 최우선 읽기 문서로 지정한다. `docs/regression-guardrails.md`에 fresh quote, provider-free Home live, valuation-band prewarm/singleflight/cache 계약을 명시한다. 반복된 문제가 기존 테스트를 통과했다면 해당 테스트를 강화하거나 새 회귀 테스트를 추가하지 않고는 완료로 보지 않는다.

## 2026-10-02 — 관세청 수출 모멘텀 API
- Toss 수출 화면은 브라우저에서 data.go.kr를 직접 호출하지 않는다. 공용 FastAPI가 서비스키를 환경변수에서 읽고 `/api/export-momentum`으로 정규화된 JSON만 제공한다.
- 환경변수는 기존에 저장한 `CUSTOMS_TOTAL_API_KEY`를 우선 사용하고, `DATA_GO_KR_SERVICE_KEY` / `CUSTOMS_API_KEY`도 호환한다. 키 값은 응답·로그·GitHub에 노출하지 않는다.
- 수출입총괄 API는 최근 24개월을 12개월 이하 구간 두 번으로 조회해 최신 12개월 수출액과 전년동월비를 계산한다.
- 품목은 HS 프록시(반도체 8541+8542 등)임을 명시한다. 기업 실제 수출액 또는 MTI 공식 주력품목 수치로 표현하지 않는다.
- 품목별 국가별 API는 HS 계층이 여러 단계로 반환될 경우 최단 HS 레벨만 합산해 중복 집계를 피한다.
- 현재 승인받은 3개 월간 API에는 1~10일/1~20일 잠정치가 없으므로 월간 데이터에서 해당 값을 추정하거나 생성하지 않는다.
- 공유 메모리 캐시는 1시간 TTL이며 stale 데이터가 있으면 즉시 반환하고 백그라운드에서 재검증한다.

## 2026-10-02 — 수출 총괄과 HS 상세의 발표시차 분리
- 관세청 총괄 월 데이터와 HS 품목/국가 데이터는 같은 시점에 최신 월이 열리지 않을 수 있다.
- 화면의 총수출 기간은 최신 완결 총괄 월을 유지하고, 품목/국가는 각 API에서 실제 행이 존재하는 최신 월을 최대 3개월까지 후퇴 탐색한다.
- 품목 API의 HS 필드는 응답에 따라 `hsCode` 또는 `hsCd`를 허용한다.
- 품목은 한 달 전체 HSK 행을 한 번 받아 필요한 HS prefix를 서버에서 집계한다. 4자리 prefix를 API에 직접 넣어 빈 결과를 정상값으로 오인하지 않는다.
- 품목/국가 상세 기간이 총괄보다 늦으면 `itemPeriod` / `regionPeriod`로 별도 노출한다.

## 2026-10-02 — 수출 품목의 금액·물량·단위가치 분해
- 관세청 HS 상세의 `expWgt`(순중량 kg)를 보존해 품목별 수출중량과 전년동월비를 제공한다.
- `unitValueUsdPerKg = expDlr / expWgt`를 계산하고 전년동월비를 제공한다.
- 이 값은 개별 제품의 판매가격이 아니라 동일 HS 그룹 내부 품목 믹스가 반영된 평균 단위가치이므로 UI에서 ‘kg당 신고금액/평균 단위가치’로 표기한다.
- 반도체·선박처럼 kg당 값의 경제적 의미가 제한적인 품목도 원자료 기반 보조지표로만 제공하며 실제 제품 ASP로 표현하지 않는다.

## 2026-10-02 — HS2 수출 확산도와 3개월 모멘텀
- 기존 6개 대표 품목 외에 같은 월 전체 Itemtrade 응답을 HS 2단위로 묶어 수출 증가/감소 확산도를 계산한다.
- 별도 관세청 호출을 추가하지 않고 이미 받은 당월/전년동월 품목 행을 재사용한다.
- HS2 확산도는 전년동월 비교 가능한 품목의 증가/감소/보합 개수, 증가 품목 비율, 증가 품목의 현재 수출 비중을 제공한다.
- 기여 품목은 투자 점수나 추천 순위가 아니라 전년동월 대비 수출금액 증감액(delta USD) 기준으로 상승/하락 각각 표시한다.
- 품목 상세는 최근 3개월 YoY 평균과 직전 3개월 평균 차이(pp)를 계산해 수출액·물량·평균 단위가치의 가속/둔화를 설명한다.
- 12개월 phaseHistory는 물량 YoY와 평균 단위가치 YoY의 부호 조합만 사용하며 미래 방향을 예측하지 않는다.

## 2026-10-02 — 반도체 HSK 세부분류
- 반도체 상세에서 2026 HSK 공식 분류를 사용해 메모리/IC 세부 항목을 별도 조회한다.
- DRAM은 HSK 8542321010, SRAM은 8542321020, Flash memory는 8542321030을 사용한다.
- HBM은 2026 HSK에서 독립 품목번호가 아니므로 ‘HBM 수출액’으로 별도 집계하지 않는다. DRAM/복합구조 메모리 등 신고 분류에 포함될 수 있음을 안내한다.
- NAND도 독립 HSK가 아니라 Flash memory 분류 안에 포함되므로 ‘Flash memory (NAND 포함)’처럼 표시한다.
- 세부 반도체 조회는 semiconductor 품목 상세을 열 때만 실행하고 기존 6시간 상세 캐시에 포함한다.

## 2026-10-02 — 반도체 HSK 조회기간 제한 대응
- Itemtrade는 시작~종료 조회기간이 1년을 넘으면 오류 99를 반환한다.
- 반도체 세부 12개월 YoY를 만들 때 최근 12개월과 전년 12개월을 각각 별도 호출한 뒤 서버에서 결합한다.
- 24개월을 한 요청으로 보내지 않는다.

## 2026-10-02 — 반도체 HSK 추가 호출 제거
- 직전의 ‘세부 HSK를 12개월+전년12개월로 별도 조회’ 방식은 정확하지만 첫 상세 로딩이 너무 느려 폐기한다.
- 메인 수출 스냅샷 생성 시 이미 확보한 최신 itemPeriod 전체 HSK 행과 전년동월 행에서 DRAM/Flash/SRAM/프로세서·컨트롤러/기타 IC를 계산한다.
- 반도체 세분화 자체는 provider 추가 호출 0회다. 상세 API는 기존 12개월 대표 반도체/국가 분석만 수행하고 세부분류는 메인 캐시를 복사한다.
- 세부 HSK 카드는 현재월·전년동월 비교만 제공한다. 세부 HSK 자체의 12개월 시계열은 성능 대가 없이 공급 가능한 별도 소스가 생기기 전에는 만들지 않는다.

## 2026-10-02 — 증권사형 반도체 수출 리포트
- 최신 itemPeriod의 전체 품목 원자료에 직전월 원자료 1회만 추가해 반도체 세부의 YoY와 MoM을 함께 계산한다.
- 메인 리포트 핵심 항목은 메모리 IC(854232), DRAM(8542321010), Flash memory(8542321030), MCP/복합구조칩 메모리(8542323000), DRAM 모듈(8473304060)이다.
- 각 항목은 수출액, 수출 YoY/MoM, 순중량 YoY/MoM, kg당 평균 신고금액 YoY/MoM을 제공한다.
- HBM은 독립 HSK가 없으므로 별도 수출액을 생성하지 않는다.
- 관세청 월간 상세 통계와 TRASS 잠정치는 집계시점/분류가 달라 숫자가 다를 수 있음을 UI에서 명시한다.

## 2026-10-02 — 반도체 MoM 경량화
- 직전월 전체 HSK 원자료 조회는 콜드 워밍을 약 97초까지 늘려 폐기한다.
- MoM은 리포트 핵심 5개 코드(854232, 8542321010, 8542321030, 8542323000, 8473304060)만 병렬 조회한다.
- 최신월/전년동월 전체 품목 원자료는 기존 수출 확산도와 대표 품목 계산에 그대로 사용한다.
- 개별 MoM 조회 실패는 전체 수출 스냅샷을 실패시키지 않고 해당 MoM만 null로 둔다.

## 2026-10-02 — 수출 콜드 워밍 경량화
- 최신 품목 상세월 탐색에서 월 전체 HSK 테이블을 후보월마다 내려받지 않는다.
- DRAM HSK 8542321010 단일 코드로 최신 상세월을 probe한 뒤, 실제 데이터가 있는 월만 전체 HSK를 조회한다.
- 최신월 전체 HSK와 전년동월 전체 HSK는 병렬로 받고, 반도체 MoM 핵심 5개 조회도 같은 병렬 구간에서 수행한다.
- 기존 _find_item_period는 호환 래퍼로 유지하되 운영 snapshot 생성은 lightweight candidate 탐색을 사용한다.

## 2026-10-02 — 반도체 세부 품목 × 국가
- 품목별 국가별 API는 국가코드가 필수이므로 전세계 순위를 가장한 화면을 만들지 않는다.
- 반도체 국가 분석은 DRAM, Flash memory, MCP, DRAM 모듈 4개 품목과 중국·홍콩·베트남·대만·미국·일본 6개 지정시장으로 제한한다.
- 각 조합에 현재월/전년동월 수출액을 조회해 YoY, 전년동월 대비 증감액, 해당 품목 전세계 총수출 대비 비중을 계산한다.
- 국가 분석은 별도 endpoint + 12시간 서버 캐시로 제공하며 메인 수출 snapshot과 품목 12개월 상세의 초기 로딩에 포함하지 않는다.
- ‘최대 시장’, ‘증가 기여’, ‘감소 기여’는 6개 지정시장 안에서만 계산한다.

## 2026-10-02 — 10일 단위 잠정 수출 레이더
- 관세청 ‘수출 주요품목별 10일 단위 잠정치’는 별도 endpoint로 제공하고 월간 HS 상세와 합치지 않는다.
- 최근 14개월을 한 번 조회해 1~10일, 1~20일, 월전체의 같은 구간 YoY와 전월 같은 구간 비교를 계산한다.
- itemUsdAmt00은 전체, itemUsdAmt01~10은 관세청 자체 10대 수출품목 분류다. 원 단위는 천달러이며 서버에서 십억달러로 변환한다.
- 반도체 비중은 같은 체크포인트 전체 수출 대비, 증가 기여는 전년동월 같은 구간 전체 수출 증가액 대비 반도체 증가액으로 계산한다.
- 체크포인트 ‘가속’은 현재 체크포인트 반도체 YoY에서 직전 체크포인트 반도체 YoY를 뺀 %p다.

## 2026-10-02 — 월말 착지 범위 모델
- 10일 단위 잠정치 72개월 이력으로 1~10일/1~20일 누적액의 월말 완성률을 계산한다.
- 중앙 추정은 최근 최대 60개월 완성률의 중앙값, 범위는 완성률 25~75% 분위수로 계산한다.
- 월말 범위는 부분수출액을 완성률 분위수로 나눠 산출하며, 높은 완성률 분위수는 낮은 월말 범위값에 대응한다.
- 예상 YoY는 전년동월 월전체 잠정치를 기준으로 계산한다.
- 최근 최대 24개월은 각 과거 시점보다 이전 데이터만 사용해 재추정하고 중앙 절대오차와 범위 적중률을 계산한다.
- 최소 12개월 유효 완성률 표본이 없으면 추정을 생성하지 않는다.
- 월말이 이미 발표된 달은 20일(없으면 10일) 시점 추정과 실제 마감값을 비교하는 final-review 모드로 제공한다.


## 2026-10-04 — Signed Customs balance and explicit relation retry
New bugs coordinated with approved Toss insight plan. `_hs_prefix_metric` leaf de-duplication used a zero default in max, dropping negative balPayments. Initialize from the actual first value so deficits remain signed; retain existing exact-parent and shallow HS hierarchy behavior. No frontend recomputation or Web UI change. Regression tests cover mixed/all deficits, duplicate leaf and wrong month, parent hierarchy.
Relationship evidence accepts optional force=false. Explicit user retry bypasses relationship and upstream news cache; normal requests keep original TTL and provider bounds. Existing callers and API response shape remain compatible. 57 focused Python tests passed and frontend bundle --check passed. Production reconciliation must confirm same-period exports-imports=balance after exact revision deployment.


## 2026-10-04 — DRAM 현물가 공개 최신값 + 자체 누적
- `/api/memory-spot`은 TrendForce 공개 DRAM Spot Price 페이지의 최신 표에서 DDR5 16Gb, DDR4 16Gb, DDR4 8Gb 세션 평균가·변동률·고저가만 읽는다.
- TrendForce 유료 역사 데이터는 역으로 수집하거나 재배포하지 않는다. Chart View가 공개 최신값을 확인한 날짜부터 일별 스냅샷을 자체 누적한다.
- 수집은 Home/시세/히트맵 경로에 연결하지 않고 메모리 수출 화면이 열릴 때만 lazy 호출한다. 6시간 서버 캐시와 15분 HTTP 캐시를 사용한다.
- 동일 sourceDate는 덮어써 중복을 만들지 않는다. Render Key Value가 있으면 별도 namespace에 최대 365개 관측을 보존하고, 없으면 프로세스 메모리로 degrade한다.
- 원문 수집 실패 시 마지막 검증값/자체 누적 이력을 유지하며 stale로 명시한다. 원문 URL과 기준일을 응답에 포함한다.


## 2026-10-04 — DRAM 공개소스 실패 재시도 제한
TrendForce 공개 최신 페이지가 일시적으로 차단되거나 실패해도 `/api/memory-spot` 요청마다 공급자를 다시 호출하지 않는다. 마지막 검증값/부트스트랩을 stale로 유지하고 15분 동안 같은 fallback을 재사용한 뒤에만 공급자를 다시 확인한다. 정상 최신값의 기존 6시간 캐시는 유지한다. Home/quotes/export-momentum 요청 경로는 변경하지 않는다.


## 2026-10-04 — 메모리 가격 카탈로그 확장
- 기존 DRAM 3종 전용 `/api/memory-spot`을 schemaVersion 2 카탈로그로 확장하고 `/api/memory-prices` 별칭을 추가한다.
- 공개 숫자가 확인되는 TrendForce 최신 표만 수집한다: DRAM 칩, DRAM 모듈, GDDR, NAND SLC/MLC 칩, NAND TLC 웨이퍼.
- HBM, MCP, eMMC/UFS는 공개 최신 가격표에서 독립 숫자형 가격이 확인되지 않으므로 가격을 추정·대입하지 않고 `unavailablePriceSeries`로 명시한다.
- MCP는 가격 대신 관세청 HSK 수출액·YoY·MoM·단위가치를 반도체 화면에서 계속 제공한다.
- 유료 과거 가격은 backfill하지 않고, 공개 최신값의 공급자 기준일을 Chart View가 자체 누적한다.

## 2026-10-05 — Guru financial criteria and dated evidence
New behavior: independent annual Buffett/Lynch-inspired Chart View criteria, cache-only evidence API, content-version conflict handling and bounded OpenDART collection. No visitor request performs financial collection. ROE uses total net income / average total equity; leverage is total liabilities/equity. Lynch PER is dated close / annual EPS and PEG uses past three-year percent growth, never TTM/forward labels.
Fresh review reproduced four issues now covered by regressions: refresh fairness, provider-failure eligibility, real full-year observation dates and unresolved real-estate type. Full account monetary values are paired with major-account income dates from the same receipt/basis; unknown or shortened annual/comparative periods do not pass. KIND financial/confirmed REIT types are excluded; unresolved real-estate types are insufficient. Preserve old evidence on failure but exclude failed verification from current matches. Existing Web bundle unchanged; Toss integration is separate.

## 2026-10-05 — Five strategies and portable Codex handoff

Classification: user-approved new additive behavior. Original Buffett/Lynch formula/price/API contracts preserved under cv-gurus-v2; add O'Neil annual plus reported-three-month growth/breakout subset, Minervini trend template adaptation and explicit Greenblatt ROA/PER alternative. A necessary annual failure permits no extra quarterly provider request. Quarter EPS is never cumulative subtraction and Q4 remains unverified rather than synthesized. Daily High/Low, prior55-session pivot, prior50-session volume and253-session history are verified; RS uses same-date positive-close ordinary-company cohort, >=90% valid histories and midrank ties. Missing quote/history stays insufficient in the full2652-universe partition. Local actual collection found2050 eligible histories/2253 dated-close companies, Minervini80 and Greenblatt3; nine O'Neil necessary-quarter verifications remain before production completion. The first Yahoo pass had missing/newly-listed/invalid histories and some provider failures; bounded missing-only retry preserved good bars and the unchanged90% floor. No provider I/O was added to viewer, Home, quotes or existing Web UI. Add checkpoint merge, bounded Actions extension stage and new-PC setup/data/secret/deployment handoff; current manual Render publishing and native Toss gates remain distinct from implementation.

## 2026-10-05 — Five-method actual quarterly and deployed checkpoint

The nine necessary-quarter checks completed using the existing private Actions key: eighteen requests, no provider errors, seven verified source comparisons and two insufficient reports. No pending records remain. Two companies pass quarterly growth but neither has the required recent volume breakout; O'Neil zero matches is correct. Independently rechecked all80 trend matches and three quality/value alternative matches against stored provider values. Data182cbdf snapshotca7bc07a7c3d4b261df3 was tested (448 Python passes, bundle parity), manually deployed and exact-health/assets/API200/409 verified. Add dated counts/source/CI/deploy evidence to the implementation report and portable handoff. Do not treat this historical checkpoint as a future realtime price or an automatic-publication/native-launch completion.

## 2026-10-06 — Valuation API exposes TTM ROA for dated annual-screen cross-check

**Classification:** additive data-semantics behavior. The Greenblatt reference screen remains a dated annual ROA/PER alternative; its full-market annual selection math is not silently replaced.

**Decision:** `/api/valuation` now exposes `roa` with field-level provenance. Prefer trailing net income divided by the latest reported total assets from Yahoo Fundamentals, with provider return-on-assets only as a fallback. The period is explicitly labeled `TTM net income / latest reported assets`. Existing trailing/forward PER semantics, cache/freshness paths and quote behavior remain unchanged.

**Protection:** this metric is for an explicit current cross-check of already selected annual candidates. It must not be presented as a complete TTM rescreen of the full KIND universe unless a versioned bulk TTM dataset and criteria are implemented. Missing values remain missing.

## 2026-10-06 — Semiconductor segment delta/trend API

- Additive endpoint `/api/export-momentum/semiconductor-trends` serves cached 12-month HSK segment history, current/prior export amounts, YoY delta amount and explicit contribution bases.
- The main `/api/export-momentum` snapshot only gains `priorExportsUsdBillion` and `deltaUsdBillion`; it does not fetch 12-month segment histories or block the existing monthly response.
- Overall contribution uses the HS 8541+8542 semiconductor net YoY change only for partial top-level observed categories. Memory children use HS 854232 memory net change. DRAM module 8473304060 has no semiconductor-total contribution.
- Provider work is cached for 12 hours and starts on explicit semiconductor analysis demand rather than Home/overview startup.
## 2026-10-06 — Compare date boundary and price-basis audit

Classification: custom-range calendar handling is a new bug; latest/regular-close wording is a regression of the existing quote-semantics contract. Reproduced with six failing tests before the fix. Yahoo requests use market-local day boundaries; returned points outside requested local dates are removed before baseline/return calculation. Existing adjusted-close, caches, stale-while-revalidate, singleflight and previous-result retention remain unchanged. Add requestedRange and exchangeTimezone metadata without removing fields. Naver CLOSE is insufficient evidence of a regular close when its timestamp is late or absent; preserve the validated 15:30 close fixture and separated after-hours values. No Web bundle/UI change. All 459 Python tests and bundle parity pass; exact Render revision/API verification follows tested main publishing.

## 2026-10-07 Official EPS labels and incremental disclosure scope

Canonical Basic EPS combined basic/diluted labels are accepted only when explicitly identifiable; diluted-only/preferred/custom/ambiguous accounts remain rejected. Existing raw reports are re-normalized without advancing financial checkedAt or changing non-EPS values. Opt-in --refresh-actions uses the same existing DART request/deadline budget before annual collection and scans only a <=31-day gap. Complete pagination/receipt/corp/date validation is atomic; failure keeps original scopes, new action/financial filing blocks EPS comparison. Daily existing workflow defaults to the incremental phase; provider I/O remains outside visitor/guru endpoints. Merge requires unchanged financial evidence, matching reviewBase and newer action proof, preserving newer annual receipts and unknown events. Missing-only annual collector/quarter math/RS90%/criteria unchanged. No new LLM key/API.

## 2026-10-07 Canonical full heatmap warm seed

US 17→21→40 cold population is normal bounded provider progress, but cannot be the only first display when verified full observations exist. Existing FULL_HEATMAP_CACHE now warms from a validated saved canonical /api/heatmap/full response, not legacy heatmap.json prices. scripts/save_full_heatmap_snapshot.py makes one ordinary request (hard60s/1MB; max3 optional) and preserves the old file on partial/invalid/error. Existing home snapshot workflow saves the complete asset best-effort every15min; no fresh flag, workers, fanout, Render secret or new LLM API. Runtime requires timezone-bound provenance/finite values/correct counts, no future or >48h asset/observations, filters current20KR40US universe, and marks snapshot rows stale/cache timestamp0. Current canonical newer/equal Home observations win; existing demand-driven refresh remains. Toss reads the same validated CDN asset optionally on full-map entry so static updates do not require automatic backend deployment. Disk seed is additive; manual Render exact-revision publishing remains unchanged. Snapshot dates/prices/change/basis are never advanced or inferred.

## 2026-10-07 Official reception date versus receipt identifier

A bounded actual global DART scan returned status000/1250 filings13pages, but row0 had a valid in-window reception date and a receipt identifier with a different date prefix. The new incremental helper had assumed an equality not guaranteed by official API docs. Remove only that assumption: rcept_no is a unique14-digit identifier; rcept_dt is the authoritative validated reception date. Keep exact corp binding, duplicates/real dates/window/pagination/atomic failure protection and financial source dates unchanged. Target45 tests/whole564 tests protect mismatch-at-last-page corporate events and immutable annual evidence. This corrects a new collector bug, not a relaxed selection or financial criterion.


## 2026-10-08 — Codex transfer audit documents existing publication guard

Classification: documentation correction to match the reviewed frontend older-publication guard; no backend code, provider data or deployment configuration change. Link the Toss repository Codex tool/skill transfer guide. Same-day CDN result/evidence publication can precede the manually deployed backend, producing a correct409. Latest-result recovery must not downgrade the newer publication to an older server snapshot; publish the exact tested data revision and verify same-version200. Preserve daily collection versus manual deployment distinction and native release gates.


## 2026-10-08 — Guru source coverage and conservative collection repair

Classification: confirmed existing parser/collector/batch-processing bugs plus a failed-refresh merge regression; criteria and visitor API contracts are preserved. Restore only explicit total Basic EPS from canonical combined or permitted nonstandard labels, and invalidate continuing/discontinued/monetary IFRS impostors while retaining source reports/periods/currency/checkedAt/non-EPS accounts. Remove the fixed twenty-page corporate-action ceiling, require complete identity/date/count/page proof inside the existing shared budgets and retain unknown on error. Preserve newer failed-attempt metadata at equal financial checkedAt only against identical annual evidence. Ignore only wholly empty leading Yahoo batch padding, never partial/internal gaps or missing dated observations.

Actual local trade-date2026-10-07 backfill adds45 valid histories and42 independently quote-matched peers, while prior2129 histories,2252 price-cohort and90% minimum remain. EPS21 observations restored and86 mistaken values invalidated. Snapshot96bf0f872bbc824f049b: Buffett54/Lynch41/O'Neil1/Minervini82/Greenblatt3. New Minervini candidate Kukdo's own bars are unchanged; repaired peer coverage moves RS69.6873→70.0096. Reject all79 zero-volume fallback quotes and the resulting five false candidates. Do not promise selection increases or treat absent evidence as no action.

Local pytest627/Node38/target175 and independent2948 source assertions pass. Actual Samsung twenty-page causation remains unconfirmed: fake21-page proof establishes the code defect only. Official bounded11-company Actions collection (Samsung plus10 unique financial-refresh targets;500request/1200sec limits), final CI/exact-main manual Render publication and same-version API/UI checks are pending and must be recorded separately. Optional --symbols requires --collect and current KIND identity, uses the existing DART Secret and budgets, preserves the universe and avoids unrelated global scans. No new LLM API, hook, paid infrastructure or threshold reduction. See GURU_DATA_COVERAGE_REPAIR_2026-10-08.md for source evidence, dated results, exclusions and portable Codex setup links.
