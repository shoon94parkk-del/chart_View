# V41.3 Resilience Polish

## Audit findings
After V41.2, the remaining high-value issues were not another visual redesign but failure-state and interaction inconsistencies in MY News: refresh failure could leave the feed empty, refresh had no busy state, freshness was unclear, filter/sort state was visually clear but weaker for assistive technology, and provider URLs were trusted without a final client-side protocol guard.

## Changes
- Preserve the previously rendered news feed when a refresh fails and label it as stale instead of replacing useful content with an empty panel.
- Show the last successful refresh time.
- Disable and animate the refresh control while a request is active to prevent repeated refresh requests.
- Add explicit tab/pressed/busy accessibility state to MY controls.
- Permit only HTTP/HTTPS external article links at the final UI boundary and keep noopener/noreferrer.
- Add offline messaging while retaining the existing screen.
- Add keyboard focus, dark-mode stale-state styling, mobile polish, and reduced-motion behavior.

## Compatibility
No API schema, provider, ranking, watchlist localStorage schema, detail flow, V41.2 summary, or 5D market-context calculation was changed.

## Files
- `static/js/resilience_v41_3.js`
- `static/css/resilience_v41_3.css`
- `static/js/home_watchlist_boot_v32c.js`
- `tests/test_v41_3_resilience.py`

## Version marker
`data-resilience-version="v41.3"`

## Rollback
Remove the V41.3 JS/CSS loader entries and the V41.3 assets. No backend or data migration rollback is required.
