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
- Daily unique-browser totals must use Render Key Value when CHARTVIEW_ANALYTICS_REDIS is configured; they must survive web-service deploy/restart. activeNow and activeHome stay process-memory heartbeat state.

- Automation/Playwright browsers must not contribute to visitor counts; `visitor_v66.js` exits when `navigator.webdriver` is true.


## Home today-change semantics
- Any field labeled 오늘/Today must be previous trading close -> current/latest regular-session price, not a 5D/1M chart-range return.
- Persistent Home snapshot: KR uses Naver fluctuationsRatio; US uses the last two valid Yahoo daily closes.
- A 5d Yahoo request must not use meta.previousClose or meta.chartPreviousClose to populate Home change.
- Korean current quote surfaces must bind the installed realtime_korea patch, not a pre-patch imported function reference.

- Persistent analytics uses only salted anonymous daily browser hashes in Render Key Value; do not store raw browser IDs or identifying profile data.


## Context-aware sharing
- Public sharing must never emit the retired `chart-view-bsg6.onrender.com` host.
- The document canonical URL is the public-host source of truth for share links; do not add another stale hard-coded production URL if it can be avoided.
- Sharing from AI PICK must include `tab=screener&view=ai-picks` and reopen the PICK ledger on receipt.
- Sharing an open stock detail must include `tab=chart&view=detail&symbol=<ticker>`; include name when available.
- Sharing a normal app screen must preserve its active tab rather than always returning recipients to Home.
- UTM parameters may be appended, but they must not replace or erase route parameters.

- 전체 히트맵 응답에서 `source=precomputed-us-heatmap` 또는 legacy heatmap.json의 price/change가 사용자 표시값으로 노출되면 회귀다.
- 홈/전체 히트맵 중복 종목은 price와 change가 동일해야 한다. provider 갱신 시점 차이보다 Home 표시 스냅샷 정합성을 우선한다.
- 전체 히트맵 refresh 실패 시 오래된 legacy 시세를 fallback하지 않는다. 이전 canonical provider/Home 값만 stale fallback으로 허용한다.

- `/api/home-live` must never await provider I/O or call `fetch_quote_snapshot` on the request path. It returns shared memory immediately and may only wake the background worker.
- `/api/home-live` remains `Cache-Control: no-store`; clients may poll the lightweight shared snapshot but must not receive a proxy-stale copy.

- Home/full-heatmap/market-now 백그라운드 provider refresh는 foreground request와 기본 thread pool을 공유하지 않는다. 전용 `BACKGROUND_MARKET_EXECUTOR`를 사용한다.
- `/api/activity` heartbeat는 Redis 영속화 완료를 기다리지 않는다. 메모리 기록 후 즉시 응답하고 persistent count는 background task로 저장한다.
- `/api/quotes`는 신선한 `HOME_LIVE_CACHE` 대표종목을 다시 provider에서 조회하지 않는다. 공용 시세 재사용 후 누락/오래된 종목만 fallback 조회한다.

- Toss 기본 분석 세트(005930.KS, NVDA, AAPL)의 1mo compare와 valuation은 startup background warm을 유지한다. 이 prewarm은 foreground/default executor가 아니라 BACKGROUND_MARKET_EXECUTOR를 사용해야 한다.
- compare cache TTL은 300초를 유지한다. 1d 5m 차트에도 5분 캐시는 해상도와 일치하며, Home 실시간 시세와 역할을 분리한다.

## PICK monitoring
- Never rewrite historical `ai_daily_rankings.json` merely to change a post-publication monitoring state.
- Synchronizing a PICK baseline must preserve an existing `KEEP`, `WATCH`, `SELL_REVIEW`, or `EXIT` state.
- Price decline, RSI, moving-average breaks, volume decline, foreign selling, or a single target-price cut cannot independently trigger `SELL_REVIEW`.
- `EXIT` must never be generated without explicit user finalization.
- Missing legacy thesis details are marked incomplete rather than inferred.

## PICK monitoring P1 evidence/UI
- KEEP/WATCH/SELL_REVIEW must come from a completed evidence review; do not infer KEEP merely because no bad headline was found.
- Evidence used for a post-PICK state must be verified, linkable, and dated on or after the PICK date.
- One ordinary negative signal can produce WATCH, not SELL_REVIEW. SELL_REVIEW requires one material verified fact or two independent negative signals.
- The monitor UI must say `매도검토`, never present it as an automatic sell order, and must surface the evidence and last review date.
- Unreviewed PICKs remain visibly `검토 대기`.
- The existing AI PICK performance ledger remains intact; PICK monitoring is an additional view, not a replacement.

### Per-ticker live quote freshness
- One successfully refreshed Korean ticker must never make every Korean cached ticker eligible for reuse. Cache-hit freshness is evaluated by ticker, not only by market.
- A seeded Home snapshot may paint immediately but must not advance live freshness timestamps.
- During the Korean NXT quote window (08:00–20:00 KST), Home/watchlist current-price paths must remain on active-market freshness rules; they must not fall back to the closed-market 5-minute cadence at 15:30.
- If `/api/quotes` fetches a newer Home-major quote from the provider, it must update the shared in-memory row and that ticker's freshness timestamp.

### OpenDART performance / Samsung guardrail
- Runtime DART requests must prefer the checked-in stock-code→corp-code cache; do not reintroduce cold-request downloads of the entire corpCode.xml archive.
- After OpenDART identifies the latest annual report, fetch narrow DART viewer sections before considering a full-report document download.
- Tables containing both a business division and a major-product list must attribute the disclosed revenue to the division, not to every listed product.
- DART triangle-negative values (△) are negative. Internal-transaction elimination rows may reconcile disclosed segment shares above 100%; use them for validation but never expose them as revenue items.
- Samsung Electronics 2025 annual-report sentinel: sourceMode=opendart-api, basis=사업부문별 매출, top item=DX 부문, share=56.3.
- Performance sentinel: optimized cold path should remain under 15s in CI; warm in-process cache under 100ms.
- A validated annual-report row remains usable after the static generator's `updated` date ages; unchanged filings must not trigger a full report parse.
- Runtime cache entries are keyed by stock code and retain the validated receipt number. Recheck the latest receipt in the background after 24 hours; parse only a changed receipt. Provider or parser failure must preserve the last validated row.
- Render Key Value is an opportunistic shared cache for all visited Korean stocks. The checked-in major-company rows remain the durable fallback because the free Key Value instance has persistence disabled and may evict keys.
- Toss share previews must include server-rendered Open Graph title/description/image before redirect. The destination must preserve the exact stock ticker or route; do not trust a user-supplied company name in metadata.
### OpenDART financial history
- Never calculate quarterly growth from a 3-month value against a cumulative prior period. Annual years must come from one filing, and interim YoY from matching cumulative fields.
- Do not mix consolidated and separate financial statements or currencies in one trend. Missing or ambiguous accounts fail closed.
- A stale validated financial cache remains visible while rechecking; a failed check must not replace it with an empty result.
- The checked-in major-company financial cache must stay valid and serve before network I/O after a cold restart. The daily generator must not churn commits when the underlying filings are unchanged.
- 직접 거래 단서는 특징주·장마감 등 다종목 기사의 수주/계약 단어만으로 생성하지 않는다. 단일 기업의 구체적 계약·납품 문맥과 상대 회사명이 함께 확인되어야 하며, 긴 회사명 안에 포함된 짧은 상장사명은 독립 상대가 아니다.

### Financial quality API v2 (2026-10-01)
- Optional quality data is additive, same receipt and currency as its financial report. Keep account provenance.
- Interim IS/CIS must use cumulative fields; interim CF must not use prior year-end annual values as a prior interim flow. BS compares with previous year end.
- Preserve missing vs zero, conservative account uniqueness and matched basis. A partial refresh retains validated periods and their source/quality packet together.
- Static major-company cache and Redis v2 serve before live requests. Never fabricate optional figures or infer share dilution from balance-sheet capital.

## 2026-10-01 DART revenue denominator metadata
Business-report adds optional revenueBasis (denominator, totalAmount, positiveSegmentTotal, signed adjustmentAmount, reconciled). Existing items, shares and report/source fields remain compatible. Reconciliation tolerance is 1% of disclosed total; absent component metadata is not verified. The Samsung general table now returns its existing consolidation flag and amount, matching the Hanwha period table. Samsung and Hanwha static rows were reread from official DART source and carry verified metadata for immediate cold-start display. The separate web UI is unchanged. Validation: 45 DART business/financial/cache tests plus scripts/build_frontend_bundle.py --check.

## 2026-10-01 Live QA follow-up: co-supplier relationship false positive
Production Samsung detail showed SK hynix as a direct contract counterparty based on a Broadcom/Anthropic article listing several memory suppliers. Name proximity plus a contract word in a flattened summary was insufficient. Require explicit named actor and named contract-target particles in either direction when both issuers occur in the evidence; co-supplier lists and peer comparison wording do not establish a pair. Keep established dedicated-subject customer-list fixtures valid. Ambiguous syntax is omitted rather than promoted to a direct relationship. No extra provider requests, endpoints or news fetches were added.
Regression reproduced two false positives before the fix. DART business/financial/cache plus relationship tests: 63 passed. Separate web bundle check is unchanged. Runtime deployment resets the in-process six-hour relationship cache.

## 2026-10-02 분기 실적
- singleQuarter와 누적 revenue/operatingProfit은 다른 의미다. 기존 cumulative fields를 direct quarter로 대체하지 않는다.
- Q4 차감/TTM은 동일 basis·currency 및 완전한 연속 분기를 요구한다. missing != zero; 적자/0 기준 증가율을 만들지 않는다.
- 분기 수집은 core detail API를 막지 않는다. 전부 실패를 ready/latest checkedAt으로 위장하지 않으며 기존 packet을 보존한다.

## 2026-10-02 Sector heatmap metadata
Full heatmap keeps its 20 KR / 40 US quote budget. US layout metadata supplies classification and market-cap weights only; the 40-company universe includes the largest company of every available sector before filling by cap. KR rows carry KRX industry/products from the existing local screener. No legacy price/change is promoted to a quote. Static metadata enrichment adds no provider requests; canonical quote/date/stale fields remain authoritative. Tests: test_heatmap_metadata plus existing performance isolation/home snapshot contracts, generated Web bundle check. Toss sector aggregates exclude missing/stale/unclassified/different-session rows and disclose covered universe, not official sector indexes.

## 2026-10-02 Full heatmap refresh budget
Do not refresh an incomplete or empty provider batch on every browser poll. Share successful snapshots for five minutes and retain a minimum 60-second failed/partial attempt cooldown. Fresh=true is explicit; preserve canonical quote timestamps and Home parity.


## No-repeat quote/cache/performance gate (2026-10-02)
- Quote freshness, Home live cache, provider routing, compare/valuation, valuation-band, heatmap, startup warming, and executor changes must first consult `docs/no-repeat-regression-policy.md`.
- Before editing, classify the issue as new behavior, new bug, or regression of a previously fixed behavior.
- A regression must restore the known-good contract before adding another cache/provider/refresh path.
- `/api/home-live` remains provider-free on the request path; provider refresh belongs in background workers/executors.
- `/api/quotes?fresh=true` remains the canonical direct fresh validation path. Do not weaken it just to reduce first-paint latency.
- Historical close, screener close, quote observation time, lookup time, and current quote semantics must remain distinct.
- Valuation-band startup prewarm, request coalescing/singleflight, and multi-hour caching are intentional protections against repeated expensive historical downloads.
- A repeated bug that escaped an existing test requires a strengthened/new regression test before completion.
- Use same-harness production timings only as regression evidence, not as absolute backend SLAs.

## Export momentum API
- Never expose the data.go.kr service key to browser JSON, logs, source control or Toss frontend environment variables.
- Do not add Customs calls to Home, Home startup critical warm, heatmap refresh, quote polling or stock-detail paths.
- `/api/export-momentum` must reuse its server cache; concurrent users must not fan out provider calls.
- Monthly Customs APIs cannot be presented as 10-day/20-day preliminary statistics. Missing checkpoint data remains missing.
- HS item groups must remain labeled as HS proxies and may not be relabeled as a company's actual exports.
- Country aggregation must never sum 2/4/6/10-digit HS hierarchy levels together.
- Provider/auth failure may keep a previously valid stale snapshot visible; never replace valid cached data with zeroes or fabricated values.

- 총괄 최신 월과 HS 상세 최신 월이 다르면 같은 월인 것처럼 표시하지 않는다. `itemPeriod`과 `regionPeriod`를 보존한다.
- Itemtrade 응답의 `hsCode`와 nitemtrade의 `hsCd` 필드 차이를 흡수한다.
- HS prefix 집계에서 상위 aggregate 행과 하위 행을 동시에 더해 이중계산하지 않는다.

- `expWgt`는 관세청 순중량(kg)이며 ‘개수’ 또는 ‘출하대수’로 표기하지 않는다.
- `expDlr/expWgt`는 ‘kg당 신고금액/평균 단위가치’이지 제품 ASP가 아니다.
- 중량이 0 또는 누락이면 단위가치를 계산하지 않고 null을 유지한다.
- 금액·중량·단위가치의 전년비는 동일 HS 그룹·동일 기준월의 전년동월을 비교한다.

- HS2 확산도는 동일 itemPeriod의 당월과 전년동월만 비교한다. 총괄 최신 월이 더 앞서도 섞지 않는다.
- HS 2/4/6/10단위 행을 동시에 합산해 중복 집계하지 않는다. HS2별 집계는 기존 prefix aggregate 규칙을 재사용한다.
- ‘기여’ 표시는 전년동월 대비 수출금액 증감액을 뜻하며 주가 기여, 기업 실적 기여, 투자 추천을 의미하지 않는다.
- 3개월 모멘텀은 최근 3개월 YoY 평균과 직전 3개월 YoY 평균의 차이(pp)다. 미래 수출 전망치로 표현하지 않는다.
- HS2 확산도는 기존 월 전체 품목 응답을 재사용해 provider 호출량을 늘리지 않는다.

- HBM을 관세청 HS 통계만으로 독립 수출액처럼 표시하지 않는다. 2026 HSK에는 HBM 전용 코드가 없다.
- 8542321030은 Flash memory다. NAND-only 수출액으로 오인시키지 않는다.
- DRAM 8542321010, SRAM 8542321020, Flash memory 8542321030의 공식 HSK 의미를 유지한다.
- 반도체 세부 조회는 #exports의 첫 화면이나 Home에서 호출하지 않고 semiconductor 상세 클릭 시에만 수행한다.

- Itemtrade 기간조회는 한 호출에 1년을 초과하지 않는다. 12개월 YoY 비교가 필요하면 최근 12개월과 전년 12개월을 나눠 조회한다.

- 반도체 DRAM/Flash/SRAM 카드를 위해 별도 Itemtrade fan-out을 추가하지 않는다. 최신 월/전년동월 전체 품목 원자료를 재사용한다.
- 세부 HSK 카드에 12개월 시계열이 없다고 해서 요청 시 12~24개의 provider 호출을 다시 추가하지 않는다.

- 반도체 리포트 MoM은 동일 HSK의 직전월과만 비교한다. 전년동월과 혼용하지 않는다.
- DRAM 모듈은 HSK 8473304060, 메모리 MCP는 HSK 8542323000 기준을 유지한다.
- HBM 전용 수출액을 관세청 월간 HS 원자료에서 추정하거나 합성하지 않는다.
- 반도체 리포트 추가를 위해 직전월 전체 품목 조회 1회를 초과하는 provider fan-out을 만들지 않는다.
