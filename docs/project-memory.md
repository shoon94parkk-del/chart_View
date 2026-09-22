# Chart View project memory

Last updated: 2026-09-22

This file is the durable engineering memory for the project. It records current behavior that future work must understand before changing code.

## Production topology
- Repository: `shoon94parkk-del/chart_View`
- Branch: `main`
- Web production: https://chart-view-pkv8.onrender.com
- Toss frontend: https://chart-view-toss.onrender.com
- Toss API base: Web Chart View backend unless explicitly documented otherwise.
- Old `chart-view-bsg6` Render service is legacy/suspended.
- FastAPI entrypoint: `main.py`
- Frontend: `templates/`, `static/js/`, `static/css/`
- Generated bundles: `static/js/chartview_release_bundle.js`, `static/css/chartview_release_bundle.css`

## Navigation / first load
- `static/js/ux_v3.js` owns initial routing.
- Clean root load/reload always starts on Home.
- Old `history.state` is not used for a clean root visit.
- Explicit deep links may open their requested tab/symbol.
- Back/Forward may restore in-app state and scroll.
- Home asset loading must never force navigation.
- Hidden/server-rendered chart state must not initialize chart work during app boot.

## Chart performance / reliability
- Lightweight Charts is lazy-loaded only when Analysis is opened.
- Home must not load the chart library.
- Chart cache TTL is 5 minutes.
- Common periods prefetch only when idle, with concurrency 2.
- Same-key requests share in-flight work.
- Expired cached data may remain visible while refreshing.
- Failed refresh preserves the last valid chart and exposes retry.
- Hidden chart callers do not invoke `loadData()`.

## Home hierarchy
Intentional order: Market -> Watchlist -> PICK -> News.
- Watchlist is personal and high-priority.
- PICK shows selected names first and cumulative stats second.
- Direct-company news is prioritized and visually separated from industry/indirect news.
- Home-only modules must not leak into Analysis/Discover.

## Watchlist
Primary file: `static/js/watchlist_v30.js`.
Live interaction layer: `static/js/live_quotes_v56.js`.
- The live layer is additive and loaded directly from `templates/index.html`; it is intentionally not part of the generated release bundle.
- It follows OpenStock's cache-first/polling interaction idea but uses original Chart View code and existing Chart View providers.
- Korean current quotes: unified Naver Finance/KRX-Koscom path with the existing 5-second server-side shared cache.
- Global current quotes: existing Yahoo quote path.
- While Watchlist is visible, Korean rows can refresh every 5 seconds during an open market; global/closed-market rows are slower. Home uses a slower cadence.
- The live layer updates price/day-change DOM fields in place and never requests 1-month history.
- Background/hidden/inactive tabs stop live polling.
- Current price + 1-month return are shown.
- Add/remove must persist and paint immediately.
- Adding one stock must **never refresh every existing watchlist row**.
- Opening the Watchlist screen is cache-first and must not start a foreground/full-list historical refresh.
- App boot paints cached watchlist values immediately and may quietly revalidate lightweight current quotes, but it does not start 1-month historical refreshes.
- On Watchlist entry:
  1. cached rows render immediately,
  2. stale current quotes may revalidate quietly through `/api/quotes`,
  3. 1-month returns use a separate 12-hour freshness window and only revalidate later/idle when stale.
- Explicit `↻ 새로고침` is the foreground path that may force both current quotes and 1-month returns.
- New-stock priority path:
  1. lightweight current quote via `/api/quotes`
  2. only that symbol's 1-month return via `/api/compare?period=1mo` in background
- Existing quote cache stays visible during failures.
- Home reuses watchlist quote cache rather than issuing redundant compare calls.
- Existing localStorage formats are compatibility contracts.
- Watchlist times are displayed in Asia/Seoul.
- Optional cross-device sync must not break local-only behavior.

## Screener
Core: `scripts/generate_screener.py`, `static/js/screener.js`, screener workflows.
- Discover always opens base screener, not a remembered PICK subview.
- Discover enters at the top.
- Highest-ranked result is first and visibly numbered from `#1`.
- Long lists retain a one-tap `맨 위로` control.
- Screener price is `기준 종가`, not realtime/current price.
- Trade date is shown with the close and in summary.
- Production freshness checks target `chart-view-pkv8`.
- PICK identity: symbol + numeric code are canonical.
- Display-name aliases (e.g. `LS ELECTRIC` vs `엘에스일렉트릭`) are allowed only when the name does not resolve to a different known symbol.

## Daily Chart View PICK
Data:
- `static/data/ai_daily_rankings.json`: daily selected picks
- `static/data/ai_recommendations.json`: performance/history ledger
- Home endpoint: `/api/home-bootstrap`

Rules:
- A daily publish must keep ranking and recommendation ledger aligned.
- Home uses the latest ranking day.
- Bootstrap must not serve a stale previous-day PICK after publication.
- Current cache contract is `no-cache, max-age=0, must-revalidate`.
- UI uses `오늘 선정 PICK` only when selected date equals current KST date; otherwise `최근 선정 PICK`.

## Data semantics
Keep these distinct:
- Home/watchlist/detail current quotes: latest/current quote path.
- Screener: close for screener trade date.
- Compare return: period return from provider observations.
- Lookup timestamp and underlying market trade date are separate metadata.

## Bundle / release contract
When bundled frontend source changes:
1. update source,
2. regenerate/update bundle,
3. update content-hash query token in `templates/index.html`,
4. run `python scripts/build_frontend_bundle.py --check`.

CI intentionally rejects source/bundle drift.

## Completion contract
A user-visible change is complete only when:
- regression checks pass,
- relevant mobile/browser tests pass,
- exact tested main SHA is deployed,
- `/health` reports the expected revision,
- production UI/navigation smoke passes.

## Known follow-ups
- Make screener expected-trade-date KRX-holiday aware.
- Precompute more Home valuation support data to reduce cold paths.
- Split legacy frontend bundles only with sufficient regression coverage.
- Remove old loaders/workflows only after confirming they are unreferenced and rollback is safe.
