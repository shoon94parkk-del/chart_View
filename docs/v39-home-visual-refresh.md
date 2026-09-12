# V39 Home Visual Refresh

## Goal
Improve home-screen hierarchy and visual appeal without changing market, watchlist, news, or analysis data behavior.

## Design hierarchy
1. **Market snapshot**: dark blue/cyan gradient hero surface with stronger contrast.
2. **Watchlist**: bright personalized panel with a blue/cyan accent rail and clearer stock tiles.
3. **Watchlist news**: editorial treatment; the #1 story is a dark feature card while secondary stories remain lighter.
4. **Broader analysis/content**: intentionally quieter cards so personalized/important information wins attention.
5. **Data status**: visually de-emphasized.

## Color system
- Brand/primary: blue/navy
- Secondary accent: cyan/indigo
- Positive: green
- Negative: red
- Warning/high impact: amber
- Neutral content: white/slate

Colors are used semantically rather than decorating every card.

## Responsive behavior
- Desktop keeps the dashboard hierarchy and uses larger shadows/depth selectively.
- <=720px keeps the market hero, switches watchlist shortcuts to a 2-column grid, and preserves the lead-story emphasis.
- <=390px makes watchlist shortcuts single-column for readability.
- Existing V38 news mobile button/touch behavior is preserved.
- Dark-mode overrides are included.

## Files
- `static/css/home_visual_v39.css`
- `static/js/home_watchlist_boot_v32c.js`
- `tests/test_v39_home_visual.py`

## Compatibility
- V38 personalized news logic is unchanged.
- V37 backend/provider contract is unchanged.
- V36 stock-detail navigation is unchanged.
- Canonical home order remains `market-watchlist-news-body-status`.

## Rollback
Remove the V39 stylesheet loader from `home_watchlist_boot_v32c.js` and delete `home_visual_v39.css`. No backend rollback is required.
