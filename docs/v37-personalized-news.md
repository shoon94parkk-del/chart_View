# V37 Personalized Watchlist News

## Goal
Show a compact personalized news feed on Home for the user's locally saved watchlist while minimizing copyright and provider-license risk.

## Providers
- Korea: NAVER API HUB Search > News (`/search/v1/news`)
- US / North America: Finnhub Company News (`/api/v1/company-news`)

## Display policy
Chart View returns and renders only:
- headline
- publisher/source label
- published time
- original article URL

The V37 endpoint intentionally does **not** proxy article body text, provider summaries, or article images. Clicking a card opens the original article in a new tab.

## Personalization
The browser reads `chartview-watchlist-v1` and requests news only for the user's current watchlist. The server:
1. splits Korean and US symbols,
2. queries the appropriate provider,
3. deduplicates by URL and normalized headline,
4. scores recency and event keywords,
5. returns a small highlight list and per-symbol groups.

## API
`GET /api/personalized-news?tickers=005930.KS,NVDA,AAPL&names=삼성전자|엔비디아|애플`

Limits:
- up to 12 symbols per request,
- up to 6 retained provider items per symbol,
- 5-minute in-process cache.

The endpoint degrades to HTTP 200 with provider error metadata when a provider key is absent so Home does not break.

## Required Render environment variables
- `NAVER_API_HUB_CLIENT_ID`
- `NAVER_API_HUB_CLIENT_SECRET`
- `FINNHUB_API_KEY`

Do not commit these values to GitHub.

## Home order
V37 canonical order:
1. market snapshot
2. watchlist
3. personalized watchlist news
4. broader market / stock content
5. data status

## Rollback
V37 is isolated in:
- `news_service_v37.py`
- `static/js/personalized_news_v37.js`
- `static/css/personalized_news_v37.css`

To disable the feature, remove the router include from `main.py` and the V37 asset loader/order block from `static/js/home_watchlist_boot_v32c.js`.
