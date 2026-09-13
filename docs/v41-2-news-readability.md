# V41.2 News Readability

## Goal
Improve comprehension of personalized news without pretending to summarize article bodies that are not fetched.

## Changes
- Every Home TOP3 and MY full-feed news card receives a visible `한줄 요약` block.
- The summary is explicitly labeled `제목 기준` and is generated only from the headline/event wording available to Chart View.
- The Home 5D price context now uses the full card width instead of a tiny sparkline.
- The 5D context adds visible text for total 5D move, last-2-session direction, and whether the current point sits near the period high/middle/low zone.
- The chart labels `5거래일 전` and `현재` so the time direction is immediately clear.
- Existing provider contracts, localStorage formats, news ranking, and `/api/compare?period=5d` request behavior are unchanged.

## Safety / wording
The one-line summary must not be described as an article-body summary. The UI keeps `제목 기준` visible because the app does not republish/fetch article body text for this feature.

## Regression coverage
- Static asset/version checks in `tests/test_v41_2_news_readability.py`.
- Existing V41 Playwright flow now requires a summary on every full-feed row and verifies that the Home 5D chart uses most of the mobile card width and exposes readable 5D context.

## Rollback
Remove the V41.2 CSS/JS loader lines and files. No backend, data, localStorage, or provider rollback is required.
