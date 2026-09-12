# V39.2 UI Polish

## Goal
Bring legacy/global UI surfaces into the same visual language introduced by V39/V39.1 without changing data, ranking, chart, watchlist, or navigation behavior.

## Changes
- Refined utility header/search styling with clearer focus state, stronger add button, and calmer ticker tags.
- Reworked primary tab navigation to use a stronger active state and larger mobile touch targets.
- Unified chart, period, valuation, macro, sector, and context cards with consistent radius, border, shadow, and typography.
- Normalized period/metric/sort/sector chips so selected states are easier to identify.
- Improved search-result surface depth and quick-sector grouping.
- Polished bottom navigation with translucent blur, clearer active indicator, and V39 blue/cyan accents.
- Added keyboard focus-visible treatment.
- Added dedicated mobile rules at 720px and 390px and dark-mode overrides.

## Compatibility
- V36 single-stock detail behavior unchanged.
- V38 personalized-news logic and provider contract unchanged.
- V39 home hierarchy unchanged.
- V39.1 5D news-range/watchlist treatment unchanged.
- Home ordering remains market -> watchlist -> news -> body -> data status.

## Files
- `static/css/ui_polish_v39_2.css`
- `static/js/home_watchlist_boot_v32c.js`
- `tests/test_v39_2_ui_polish.py`

## Version markers
- `data-ui-polish-v392` asset marker.
- `home.dataset.uiVersion = 'v39.2'`.
- Existing `visualVersion = 'v39'` and `visualPatch = 'v39.1'` are preserved for backwards regression compatibility.

## Rollback
Remove the V39.2 loader block/calls from `home_watchlist_boot_v32c.js` and delete `ui_polish_v39_2.css`. No backend rollback is required.
