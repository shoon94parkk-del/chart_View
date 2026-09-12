# V39.3 · P0 Clarity

## Scope
Implements only the first release unit from the V39.2 follow-up improvement plan: P0-01 through P0-03. V39.4/V39.5/V40 work is intentionally deferred so target-state changes are reviewable independently.

## Problems addressed
1. Single-stock detail and the existing comparison brief could show different stocks at the same time.
2. Home watchlist prices could be ellipsized even when the card had spare vertical space.
3. Trade basis, browser/server query time, and return period were not consistently attached to the value the user was reading.

## Changes
### Detail target vs comparison list
- `static/js/clarity_v39_3.js` captures the source app mode + scroll before V36 detail navigation.
- While a V36 detail is open, the legacy `stock-brief-v8` comparison summary is hidden to avoid presenting a second stock as though it belonged to the detail target.
- Detail gets explicit `상세 대상` and `비교목록` context pills.
- The comparison list is read-only in this V39.3 layer; opening detail does not add/remove comparison tickers.
- `밸류 보기` and `투자판단 보기` fetch evidence for the detail ticker directly and render it inside the detail surface. They do not mutate the comparison list.
- Closing detail restores the originating app mode and scroll position when possible.

### Watchlist price readability
- Home watchlist cards place the full price on its own row.
- Price values use `white-space: nowrap` and do not use ellipsis.
- Home grid is 4 columns on wide desktop, 2 columns through tablet, and 1 column at <=430px so long prices remain readable.
- Long stock names may still truncate; the price may not.

### Basis / period / query wording
- Home and watchlist cards explicitly show `1달 수익률` near the return.
- V39.3 reuses the existing `/api/compare?...&period=1mo` response to obtain each stock's actual end/trade date and displays it as a trade basis.
- Detail basis adds a separate browser query time; it is not labeled as market time.
- `방금 갱신` copy is normalized to `방금 조회` where V39.3 decorates watchlist metadata.
- Macro summary wording changes `최근 기준` to `매크로 관측 기준`, preserving the possibility that macro and market snapshot values have different observation dates.
- Watchlist direction colors use the Korean convention proposed in the plan: rise red / fall blue. Existing arrows and signs remain so state is not color-only.

## Files
- `static/js/clarity_v39_3.js`
- `static/css/clarity_v39_3.css`
- `static/js/home_watchlist_boot_v32c.js`
- `tests/test_v39_3_clarity.py`
- `docs/v39-3-p0-clarity.md`

## Verification targets
- Existing app regression suite.
- Existing mobile Playwright smoke.
- V39.3 static regression checks.
- Manual production check after deployment: Home/Watchlist/News -> NVDA detail, comparison-state label, detail close restore, long price at mobile widths, trade/query labels.

## Deferred
- Chart-first analysis layout compression (V39.4).
- Valuation table redesign and action terminology cleanup (V39.4).
- News card compression/diversity/provider-failure work and screener flow (V39.5).
- Request/init/CSS consolidation (V40 preparation).

## Rollback
Remove the V39.3 asset loader calls from `home_watchlist_boot_v32c.js`, or revert this release PR. V36/V38/V39/V39.1/V39.2 behavior remains underneath.
