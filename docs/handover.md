# Chart View 개발 인수인계

최종 갱신: 2026-09-22

## 작업 시작 전에

새 작업자는 코드보다 먼저 아래 순서로 읽는다.

1. `/AGENTS.md`
2. `docs/project-memory.md`
3. `docs/regression-guardrails.md`
4. `docs/decision-log.md`

이 문서들은 현재 구조와 이미 해결한 회귀 문제의 저장소 기반 기억이다. 기존 동작을 바꾸는 작업은 관련 회귀 테스트와 결정 로그를 함께 갱신한다.

## 운영 경로

- 운영 URL: https://chart-view-pkv8.onrender.com
- 저장소: https://github.com/shoon94parkk-del/chart_View
- 기본 브랜치: `main`
- Render 진입점: 루트 `main.py`
- 실행 명령: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 실제 템플릿/정적 자산: 루트 `templates/`, `static/`
- `toss_stock_app/`는 과거 사본이다. 현재 Render 진입점으로 사용하지 않는다.

## 앱 출시 준비 Stage 1 + Stage 2 (PR #11)

상세 설계·재현·테스트·복구 기록은 `docs/app-release-stage12.md`를 우선 읽는다.

### 현재 상태 소유권

- 비교목록·숫자 정규화·화면 snapshot: `static/js/app_state_v40.js`
- 단일 종목 상세·history·요청 취소: `static/js/single_detail_v40.js`
- 비교 수익률 차트: 기존 `static/js/chart.js` 엔진 유지
- 관심목록 저장/목록 UI: 기존 `static/js/watchlist_v30.js`, 저장 형식 유지
- 실시간 표시 보강: `static/js/live_quotes_v56.js` (활성/가시 영역의 현재가만 경량 polling, `/api/compare` 금지, 1달 수익률 캐시 보존)
- 개인화 뉴스 UI: `static/js/personalized_news_v40.js`
- 개인화 뉴스 서버: `news_service_v37.py`
- 화면 완성/접근성: `static/js/release_ui_v40.js`, `static/js/release_flow_v40.js`
- 비교 화면 압축 스타일: `static/css/comparison_ui_v40.css`
- 공통 Stage 1+2 스타일: `static/css/release_ui_v40.css`
- 활성 자산 로더: `static/js/home_watchlist_boot_v32c.js`

### 중요 호환 규칙

- `chartview-watchlist-v1`, `chartview-selected-tickers-v1`, `chartview-ticker-names-v1`, `chartview-recents-v1` localStorage 형식을 바꾸지 않는다.
- 비교목록 key가 **없을 때만** 기본 비교목록을 적용한다. 사용자가 저장한 `[]`은 빈 목록으로 유지한다.
- 단일 상세를 연다고 비교목록을 변경하지 않는다.
- 비교 버튼 상태는 `비교 중 / 비교에 추가 / 비교목록 관리`만 사용한다.
- 상세 요청은 AbortController + detail sequence로 보호한다. A→B 전환이나 닫기 뒤 A의 늦은 응답이 DOM을 쓰게 만들지 않는다.
- V39.3의 `clarity_v39_3.js`와 V36 `personalization_v36.js`, V38 `personalized_news_v38.js`는 새 활성 로딩 경로에서 제외됐다. 과거 CSS는 시각 호환 때문에 일부 유지한다.
- 뉴스는 관심종목 최대 20개 전체를 조회하며, 서버 provider 동시 호출은 제한한다. 기사 텍스트가 5거래일 미니차트보다 먼저 표시돼야 한다.
- ROE/배당률은 값 크기로 단위를 추정해 임의로 100배하지 않는다. null/빈 문자열/NaN/Infinity와 실제 0을 구분한다.

### 검증

기존 명령에 더해 PR CI에서 아래 브라우저 테스트를 실행한다.

```bash
python -m pytest -q
node --test tests/frontend.test.cjs
node tests/mobile_smoke.cjs
node tests/app_release_stage12.cjs
```

`tests/app_release_stage12.cjs`는 Playwright 격리 context에서 상세 멈춤 외부 timeout, A→B 역순 응답, 닫기 후 늦은 응답, 저장된 빈 비교목록, 6개 한도, 결측값/0, 20종목 뉴스/부분실패/미니차트 지연, 360/390/430 긴 가격, 모바일/데스크톱 차트 위치, 다크모드·키보드·저장 실패를 검사한다.

Playwright 모바일 viewport 결과는 실기기 검증으로 표현하지 않는다.

## V35 변경 목적(역사 기록)

1. 같은 화면에 있는 데이터의 수집 시각과 원자료 기준일을 구분한다.
2. 밸류에이션 필드의 실제 선택 소스와 계산 방식을 API에서 전달한다.
3. 비교 차트를 조정주가 일봉 기준으로 통일한다.
4. EPS·주가 변화율 차이를 `%p`로 표시하고 단정적인 ‘미반영’ 표현을 없앤다.
5. 투자판단은 서로 다른 판단 축 수를 사용하고 데이터 존재 비율을 신뢰도처럼 표시하지 않는다.
6. 역사적 밸류를 공시 시점 근사 재구성치로 명확히 표시한다.
7. 종목발굴·관심종목에서 진입한 종목을 요약 카드의 활성 대상으로 맞춘다.
8. 앱 셸이 준비되기 전 구형 메뉴가 잠깐 노출되는 현상을 줄인다.

## 후속 작업

- 실제 공시일을 구할 수 있는 데이터 경로를 조사해 역사적 밸류의 45일 가정을 종목별 공시일로 교체한다.
- 공급자 예상 PER/EPS가 FY1·FY2·NTM 중 어느 기간인지 신뢰할 수 있게 식별되는 경우에만 구체적인 회계기간을 표시한다.
- 뉴스 번역/사건 군집/새 투자 점수는 Stage 1 안정성 범위와 분리한다.
- 계정 동기화, 알림, 공유, PWA, 앱스토어 패키징은 별도 제품 단계다.
- 최초 앱 셸을 템플릿에 정적으로 포함시키는 구조 통합은 별도 단계로 진행한다.
- V별 패치 파일과 일회성 워크플로는 참조 여부와 복구 경로를 확인한 뒤 정리한다. 일괄 삭제하지 않는다.

## 변경 원칙

- 코드 기능 변경과 정기 데이터 캐시 커밋을 구분한다.
- 화면 수치에는 값뿐 아니라 단위, 기준일, 소스, 기간을 함께 추적한다.
- 브라우저 저장 관심종목은 계정 동기화 데이터로 표현하지 않는다.
- 배포가 확인되기 전 완료로 기록하지 않는다.
- 운영 완료는 Render `live`만으로 판단하지 않고 main SHA/revision과 화면 동작을 함께 확인한다.


## 2026-09-21 audit UX implementation

- Production URL: https://chart-view-pkv8.onrender.com
- Implemented: direct date-range validation and accessible labels, loading/empty state separation for detail charts, explicit 0% return baseline, clearer watchlist/comparison wording, and current-production CI verification.
- Release rule: keep source assets and generated `chartview_release_bundle.js` synchronized; `python scripts/build_frontend_bundle.py --check` must stay green.
- Regression focus: reversed/future dates must preserve the previous valid chart; detail must not show “차트 자료 없음” while compare data is loading; production checks must target the pkv8 Render service.\n- News summary quality gate: translated Korean summaries are no longer rejected just because the raw English headline has no token overlap; cache version is v50-quality-language.

### 2026-09-21 audit phase 3

- PICK 홈 성과는 추천 건별 단순 평균이며 평가 가능한 건만 분모에 포함한다. 홈에는 평가/전체 건수와 미평가 제외를 표시한다.
- `오늘 선정 PICK`은 서울 날짜와 실제 선정일이 같은 경우에만 사용하고, 그 외에는 `최근 선정 PICK`으로 표시한다.
- 상세 `예상 PER`은 `fieldMeta.forwardPE.period`가 있으면 그 기간을 표시하고, 없으면 `기간 미확인`을 유지한다.
- `분석 요약`은 매수·매도 점수를 만들지 않고 `관찰된 사실 / 비교할 기준 / 확인이 필요한 점`을 분리한다.
- 관심목록 시각은 `Asia/Seoul`로 명시 변환한다. 백업 복원은 기존 목록을 덮어쓰지 않고 미리보기 후 중복 제거·병합하며 최대 20개 제한을 유지한다.

### 2026-09-21 audit phase 4

- 데스크톱 주요 화면은 1120px 공통 셸을 기준으로 정렬하고, 홈 시장 본문은 넓은 화면에서 2열로 사용한다. 모바일 하단 탐색은 유지한다.
- 홈 주요 종목 가로 목록은 텍스트 로고 fallback을 유지하고 링 크기를 줄였으며, 데스크톱 이전/다음 버튼과 좌우 방향키 탐색을 제공한다.
- 홈·관심목록의 조회 시각은 `Asia/Seoul`로 명시 변환한다.
- 관심목록 백업·복원은 `목록 관리` 아래에 두고, 복원은 미리보기·중복 제거·기존 목록 보존 규칙을 유지한다.
- CV-14 검증 중 스크리너 RSI 최소>최대는 이미 입력 오류로 차단되고, 오류가 있으면 마지막 유효 customFilters를 유지하는 현재 구현을 회귀 계약으로 고정한다.

## 2026-09-21 audit final completion

- Audit source: `ChartView_UI_UX_Audit_Plan_2026-09-21.md`.
- Final gap pass: Home market summary is kept ahead of the personal watchlist, with the major-stock strip following; the watchlist survives Home snapshot repaint.
- Detail compare points now retain raw point price alongside the existing return percentage. The detail chart exposes start/middle/end dates and announces selected date + price + return for keyboard/touch navigation.
- Accessibility: detail watch/compare actions have explicit names and the interactive chart readout uses a polite live status.
- Remaining validation caveat: automated responsive/browser suites can verify 360/390/430-class behavior, but physical iOS/Samsung Internet device testing is still a release QA task rather than a code gap.


## 2026-09-22 Home heatmap V57
- Home `주요 종목 오늘 시황` now supports Card/Heatmap switching.
- V57 is standalone/direct-loaded, so rollback does not require rebuilding the legacy frontend bundle.
- Heatmap uses shared Home SWR data; do not replace it with per-tile quote fetches.
- True market cap comes from `static/data/valuation_cache.json`; old `regularMarketVolume -> marketCap` behavior was incorrect.
- Rollback branch: `backup/pre-home-heatmap-20260922`.

## 2026-09-22 Heatmap mobile correction V58
- Fixed blank Korea heatmap: Home SWR now preserves previous valid marketCap when live Korean quotes omit it.
- Logos are small inline marks beside the company name on sufficiently large tiles; no absolute white logo bubble.
- Heatmap mode hides the horizontal-card previous/next arrows and uses a mobile stacked header.
- Constrained tiles shorten labels/hide price to avoid clipping; missing market-cap rows show a refresh message instead of an empty board.
- Browser heatmap cache key moved to V58 to discard the bad zero-cap cache.
- Rollback branch: `backup/pre-heatmap-mobile-fix-20260922`.

## 2026-09-22 Heatmap true-cap V59
- Treemap weight is raw marketCap; no exponent/root/log visibility compression.
- The legend now states that tile area equals actual market-cap share within the displayed market group.
- Price text is stricter on small/short tiles to avoid the partial clipping seen on mobile.
- Browser heatmap cache key moved to V59.
- Rollback branch: `backup/pre-true-cap-heatmap-20260922`.

## 2026-09-22 Heatmap KR readability V60
- U.S. layout remains V59 raw-market-cap weighting.
- Korea alone uses `marketCap^0.82` to reduce Samsung Electronics/SK hynix dominance and keep other Korean representative names readable on mobile.
- Labels explicitly distinguish Korean visual adjustment from U.S. actual market-cap share.
- Browser heatmap cache key moved to V60; data source/cache/API behavior is unchanged.
- Rollback branch: `backup/pre-kr-heatmap-compression-v60-20260922`.

## 2026-09-22 Heatmap KR balance V61
- U.S. remains raw market-cap weighting exactly as V59/V60.
- Korea changed from `marketCap^0.82` to `marketCap^0.58` because V60 was visually too close to raw sizing.
- This restores the more balanced first Korean layout: Samsung Electronics/SK hynix stay largest, while the other representative names receive materially more readable area.
- Browser heatmap cache key moved to V61.
- Rollback branch: `backup/pre-kr-heatmap-v61-20260922`.


## 2026-09-22 Macro policy + sparkline V62
- Current Fed policy card: `FEDTARGET` from FRED daily `DFEDTARL/DFEDTARU`; separate EFFR card: `DFF`.
- Do not restore monthly `FEDFUNDS` as a “current policy rate”.
- Macro collection is still GitHub-Action precomputed every 6 hours, so runtime latency is unchanged.
- Macro mini charts are inline SVG from cached chart_data; no Lightweight Charts dependency.
- Traffic light combines inflation/Fed/labor/financial-stress/liquidity descriptively and does not predict FOMC decisions.
- Rollback: `backup/pre-macro-fed-signal-v62-20260922`.

- V62b: direct FRED CSV timed out on GitHub Actions, so DFF/DFEDTARL/DFEDTARU collection uses the Equibles FRED mirror. Keep runtime cache-only.


## 2026-09-22 Macro chart containment V63
- Fixes SVG sparkline lines escaping their macro cards on mobile.
- SVG renders at 100% x 100%; wrapper/container clip overflow; normal chart height 80px; core liquidity chart 120px.
- Negative mini-chart margins removed.
- No macro API/data/signal change; only rendering containment and asset cache bust.
- App CI macro cache expectation is 16 rows with FEDTARGET + DFF.
- Rollback: `backup/pre-macro-chart-clip-v63-20260922`.


## 2026-09-22 Cross-device sync V64
- Watchlist: on entry, one `/api/quotes` request covers all saved symbols so mobile/desktop “오늘 등락률” is complete. Subsequent high-frequency polling remains visible-only; no 1M historical fan-out.
- Cards without a current quote still render the `오늘 —` line, so row structure is consistent.
- Home Heatmap chooses the fresher of shared Home snapshot vs private heatmap cache; equal timestamps prefer Home.
- First Heatmap revalidation is prompt (short timer), not browser-idle dependent.
- Direct-loaded assets are cache-busted to V64; generated legacy bundle is untouched.
- Rollback: `backup/pre-cross-device-sync-v64-20260922`.


## 2026-09-22 Intekplus PICK correction
- Keep Intekplus (`064290.KQ`) only on 2026-09-14.
- Removed its 2026-09-17 and 2026-09-21 manual PICK records from ranking history and recommendation performance history.
- Those two dates now remain two-stock user-final selections; no replacement stock was invented.
- Validator accepts 1–3 consecutively ranked picks for `user_final_selection`; GPT-reviewed TOP3 remains exactly three.


## Intekplus correction post-refresh verification
- Validate GPT TOP3 workflow passed after source-aware validator alignment.
- The automatic `data: refresh GPT TOP3 track record` commit preserved the correction: Intekplus exists only on 2026-09-14; 2026-09-17 and 2026-09-21 remain two-name manual selections.
- This note intentionally triggers a final exact-revision production verification on top of the bot-generated data refresh.


## 2026-09-22 Home live parity V65
- Home Card + Heatmap are now driven by one shared merged live-quote state.
- Initial Home: one batch `/api/quotes` for all 18 displayed symbols.
- Open market: 5-second quote polling only for the active KR or US group; hidden/inactive Home does not poll.
- `/api/heatmap` is geometry/market-cap support and refreshes every 5 minutes, not the intraday price path.
- Global quote cache TTL is 5 seconds; Korean realtime cache was already 5 seconds.
- Browser regression asserts Samsung Card and Heatmap both move to the same +1.23% from the same live batch.
- Rollback: `backup/pre-home-card-heatmap-parity-v65-20260922`.


## 2026-09-22 Server-live + private usage V66
- Home Card/Heatmap no longer call provider-backed `/api/quotes`; they read Render's `/api/home-live` memory snapshot every 5 seconds.
- Background worker owns provider refresh: open market + active Home viewer => 5-second refresh; no active Home viewers/closed market => no provider polling.
- Watchlist live polling remains separate and Watchlist-only.
- Global anonymous heartbeat runs every 20s. Daily visitor identity is a salted hash of a random browser ID.
- Owner dashboard: `/admin/usage`; API requires `X-ChartView-Admin`. Secrets live only in Render environment.
- Daily unique-browser totals persist in Render Key Value (10-day TTL) and survive web-service deploy/restart. activeNow / activeHome are intentionally process-local heartbeat state.
- Rollback: `backup/pre-server-live-cache-v66-20260922`.

- Automation/Playwright visits are excluded from usage counts via `navigator.webdriver`.


## 2026-09-22 Home daily-change correctness V67
- Root cause of absurd Heatmap changes: GitHub Home snapshot stored Yahoo 5D chart-range return as change.
- KR snapshot: Naver Finance fluctuationsRatio.
- US snapshot: current/latest price vs immediately preceding daily close.
- main.py installs the existing Korean realtime patch before binding quote/compare/valuation helpers.
- Do not regress Home change to Yahoo 5D meta previousClose/chartPreviousClose.
- Rollback: backup/pre-daily-change-fix-v67-20260922.


## V67 generated snapshot verification
- GitHub Action regenerated `home_snapshot.json` with source `github-actions-daily-change-v67` and zero provider errors.
- Verified generated examples: Samsung Electronics +1.28%, SK hynix -1.45%, NVDA +2.299%, AAPL +0.8479%, MSFT +1.5857%.
- NVDA's prior erroneous +7.78% was Yahoo's 5D range return; it is no longer used as a Home today-change value.
- This documentation-only commit exists to pin final production CI and Render revision after the bot-generated snapshot commit.


## 2026-09-23 Context-aware sharing V68
- Fixed the share button's retired bsg6 URL.
- Public base comes from the page canonical (currently pkv8).
- Current-screen share is supported for all main tabs; AI PICK shares `tab=screener&view=ai-picks`; open stock detail shares symbol/name.
- `window.ChartViewShare` exposes the V68 URL builder/share action for regression testing.
- Rollback: `backup/pre-context-share-v68-20260923`.


## 2026-09-28 — P0 차트 SWR
- `/api/compare`의 성공 캐시는 300초 이후에도 즉시 반환하고 background refresh한다.
- refresh는 `chartview-compare-refresh` 전용 2-thread executor를 사용해 foreground/default executor를 막지 않는다.
- provider 실패 시 마지막 정상 차트를 유지한다. 최초 실패 응답만 30초 negative cache한다.
- 정규장에는 Home live refresh가 5초, 장외에는 300초이므로 성능 감사는 정규장 재검증을 별도로 수행한다.


## 2026-09-28 — P0 compare request fast path
- `get_compare_cache()` is provider-free and may be called on the event loop.
- `/api/compare` returns cached/SWR values without entering the shared `asyncio.to_thread` queue.
- Only real cache misses use worker threads and provider I/O.
- Response fields `cacheHits` and `providerFetches` are available for production verification.

## 2026-09-28 — P0 startup warm priority
- Startup awaits market-now (12s cap) and default analysis (12s cap) before readiness.
- Bulk Home live/full heatmap/Home snapshot refreshes start only after those critical caches.
- This intentionally shifts provider cost into deploy startup and prevents the first visitor from paying it.
- STARTUP_WARM logs marketReady, analysisReady, and total warm time for deploy verification.


## 2026-09-28 — P0 provider-herd removal
- Removed automatic snapshot_warmer startup from market_service package import.
- Startup warms only market-now + default analysis, then analytics; no immediate Home/full-heatmap provider fan-out.
- Home live remains active-user driven; Home snapshot/full heatmap remain endpoint SWR.
- fetch_quote_snapshot is singleflight-coalesced to deduplicate overlapping Home/live/heatmap ticker work.


## 2026-09-28 — P0 response-first refresh
- market-now stale cache returns first; provider refresh is scheduled 3s later.
- Home snapshot stale cache returns first; its 18-symbol refresh is scheduled 6s later.
- First active Home session serves seeded quotes for a 5s grace before live provider refresh.
- Latency-sensitive background executor: 2 workers. Bulk snapshot/full heatmap executor: 1 worker.
- Goal: prevent stale revalidation from delaying cache-only /api/compare and other navigation requests.


## 2026-09-28 — P0 valuation SWR
- Valuation memory cache keeps the last successful value beyond the 300s freshness window.
- Stale values return immediately and refresh on chartview-valuation-refresh (1 worker).
- /api/valuation reads cache hits synchronously and offloads only true misses.
- Response diagnostics: cacheHits / providerFetches.


## 2026-09-28 — Original Home first-paint P0
- Home snapshot cache key is v18; v17 is read once for migration.
- Home heatmap uses the shared snapshot immediately, delays geometry refresh, and avoids forcing a second /api/home-live on card insertion.
- profile-sync/status and DATA STATUS /api/macro are idle work, not first-paint work.
- AI PICK mounts after first paint, does not preload ledger assets, and only refetches on persisted bfcache pageshow.
- Re-run a fresh-browser production audit after deployment; target Home median <=1.2s and no repeated >2s spikes under ordinary off-market load.


## 2026-09-28 — Original Home first-paint P0 v2
- Hidden Watchlist no longer requests quotes during Home boot; entry refresh owns revalidation.
- Quick-add wrapper calls watchlist refresh only while Watchlist is active.
- Personalized Home news waits 2.6s before observing the below-fold section.
- Profile sync starts on Watchlist entry, with an 8s fallback.
- Heatmap geometry/Data Status/AI PICK use explicit 2.6–3.2s grace instead of requestIdleCallback.
- Generated release bundle is produced by scripts/build_frontend_bundle.py via a temporary branch-only workflow; do not hand-edit the bundle.


## 2026-09-28 — Original single boot bundle
- Original Chart View now has one versioned /static/js/chartview_boot_bundle.js startup request instead of 17 JS requests.
- scripts/build_boot_bundle.py is deterministic and must stay green with --check.
- The existing release bundle is still generated independently and embedded into the boot bundle.
- templates/index.html keeps non-loading meta version sentinels for chartview_release_bundle.js and ai_daily_widget.js so existing generated-asset checks remain valid.
- CI validates release bundle freshness, boot bundle freshness, JavaScript syntax, and the one-startup-script contract.


## 2026-09-28 — Original boot CSS P0
- Original startup now targets one JS boot request and one CSS boot request.
- chartview_boot_bundle.css preserves the prior stylesheet order: style, ux patch, promo, release CSS, continuity, live quotes, heatmap, p2 revisit.
- chartview_release_bundle.css remains independently generated and is embedded into the boot CSS; its template version is retained only as a non-loading meta sentinel.
- home_summary_v54.js is embedded before ui_continuity_v53.js.
- promo_v1.js and ui_continuity_v53.js must not dynamically reload AI/home-summary helpers when window.__CHARTVIEW_BOOT_BUNDLE__ is present.
- Re-measure production with fresh Chromium contexts; judge the change by median and worst-case Home latency, not only the best run.


## 2026-09-28 — P0 live freshness
- Do not regress U.S. current quotes back to the last closed 5m bar; prefer Yahoo chart meta regularMarketPrice/regularMarketTime.
- Korean current prices remain on realtime_korea.py.
- MARKET_NOW_TTL=12s and refresh remains stale-while-revalidate; /api/market-now must stay non-blocking on normal cached reads.
- Frontend live polling is intentionally separate from first Home paint.


## 2026-09-28 — Home/detail quote parity
- `/api/quotes?fresh=true` bypasses HOME_LIVE_CACHE and uses the canonical provider quote path.
- Keep the default `fresh=false` path for Home/watchlist first-paint performance.
- Korean stocks still resolve through realtime_korea.py; do not add another Korean quote provider.


## 2026-09-29 — Screener popular-filter data contract
- scripts/generate_screener.py now uses PERIOD='1y' so 52-week-high proximity is available.
- Do not rename macdBullish, macdCrossUp, goldenCross2060, trend2060, high52, distance52HighPct, near52High, bbBreakout without updating chart-view-toss presets/tests.
- The generated screener remains exact-trade-date fail-closed and end-of-day; popular filters must not be described as intraday signals.
## 2026-09-29 DART 재무 추이
- New `/api/financial-history` provides recent annual and cumulative interim sales/operating profit for Korean tickers. Requires existing `DART_API_KEY`; uses the checked-in corp-code cache and optional Render Key Value cache. First uncached lookup may wait for OpenDART, while subsequent lookups reuse cached data.
- Check production with Samsung Electronics and SK hynix after deploying the exact tested main revision. Verify the source filing links, accounting basis, years, and cumulative half-year comparison; report missing OpenDART data as unavailable rather than filling it from Yahoo.
- A checked-in 14-company financial cache is now generated by the scheduled DART workflow. After deploying its exact revision, verify a cold major-company `/api/financial-history` request returns immediately from static data and the background official recheck preserves the validated row.
