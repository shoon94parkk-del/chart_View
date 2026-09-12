# V38 — News Impact UI

## Goal
Turn the V37 watchlist news feed into a faster decision surface for both desktop and mobile users.

## What changed
- Home now shows only the top 3 watchlist news highlights instead of a long text feed.
- Existing V37 backend relevance score is normalized to an `Impact Score` from 1 to 100 for display.
- Impact bands: very important / important / watch / reference.
- Each card includes a short `왜 중요?` explanation inferred from event keywords.
- The top story is visually emphasized on desktop.
- For each top story, V38 attempts to read the existing `/api/compare?period=5d` response and shows a small sparkline and recent 5-day return only when real price data is available. Missing price data is hidden rather than fabricated.
- `차트에서 보기` opens the existing V36 single-stock detail via `window.__openStockDetail` without mutating the comparison list.
- `원문 보기` keeps the V37 conservative link-out policy; article bodies and images are not republished.

## Responsive behavior
### Desktop
- Lead story spans full width.
- Remaining stories use a 2-column card layout.
- Sparkline, impact score, explanation, and actions remain visible without crowding.

### Mobile <= 720px
- One-column card layout.
- Headline size and explanation density reduced.
- Actions become equal-width touch targets.

### Small mobile <= 390px
- Stock/impact header stacks more compactly.
- Action buttons become full-width rows with at least 44px height.
- Sparkline width is reduced.

## Files
- `static/js/personalized_news_v38.js`
- `static/css/personalized_news_v38.css`
- `static/js/home_watchlist_boot_v32c.js`
- `tests/test_v37_personalized_news.py`

## Compatibility
- Backend remains `news_service_v37.py`; provider credentials and API contract are unchanged.
- Home section id remains `home-personal-news-v37` intentionally so V36/V37 home-order logic and existing layout hooks do not break.
- V38 is marked by `home.dataset.newsVersion = 'v38'`.

## Rollback
Restore the V37 asset loader in `home_watchlist_boot_v32c.js`. The V37 JS/CSS files remain in the repository and the backend contract is unchanged.
