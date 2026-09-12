# V36 Personalization Foundation

Date: 2026-09-12

## Implemented

- Home priority is now market snapshot -> watchlist -> broader market/major stocks -> data status.
- Watchlist/home stock clicks open a single-stock detail surface without automatically changing the six-stock comparison list.
- The detail surface has an explicit `비교에 추가` action and shows the actual comparison range, observation count, and price-basis metadata when the API provides them.
- Cross-tab changes to watchlist/selection/name storage trigger a safe refresh so another tab does not continue showing stale personalized state.
- Watchlist freshness wording distinguishes browser query time from the underlying market basis.
- V36 assets are isolated in `personalization_v36.js/css` and loaded from the existing home-watchlist bootstrap for rollback simplicity.

## Deliberately not implemented

Personalized news is not connected yet. The approved review plan requires a provider whose public-display, caching, deduplication, transformation, and market coverage rights are confirmed first. No paid provider signup, scraping, or unapproved API integration was introduced in V36.

## Rollback

Revert the V36 commits or remove the V36 asset loader from `static/js/home_watchlist_boot_v32c.js`. The pre-V36 watchlist, chart, and home modules remain intact.

## Next implementation gate

Choose/approve a news source after documenting KR/US coverage, display fields, source-link requirements, cache retention, deduplication/transformation permission, rate limits, latency, and monthly cost ceiling. Then add server-side provider adapters and event-level deduplication behind a feature flag.
