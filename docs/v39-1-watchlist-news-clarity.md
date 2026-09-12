# V39.1 · Watchlist + News Clarity

## Goal
Keep the V39 visual direction while improving two readability issues reported after production use: the personalized news sparkline period was too easy to miss, and the Home watchlist cards still felt visually flat.

## Changes
- News sparkline keeps the existing V38 `/api/compare?...&period=5d` source.
- The visible period label is promoted to `5D · 최근 5거래일` so users immediately understand the chart window.
- Home watchlist current price is larger and heavier.
- 1-month return becomes a pill with direction icon.
- Up/down cards receive restrained green/red tint and a left-edge trend indicator.
- KR/US market badge and ticker hierarchy are strengthened.
- Mobile keeps the V39 2-column layout at <=720px and 1-column layout at <=390px.
- Dark mode receives matching contrast adjustments.

## Files
- `static/css/home_visual_v39_1.css`
- `static/js/home_watchlist_boot_v32c.js`
- `tests/test_v39_1_home_clarity.py`

## Preserved behavior
- V38 news ranking and TOP 3 selection unchanged.
- News mini-chart remains recent 5-day data (`period=5d`).
- Watchlist continues to show the existing 1-month return data.
- V39 market/news visual hierarchy remains intact.

## Rollback
Remove the V39.1 stylesheet loader from `static/js/home_watchlist_boot_v32c.js` and delete `static/css/home_visual_v39_1.css`.
