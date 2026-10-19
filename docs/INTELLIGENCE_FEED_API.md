# 3인 에이전트 시장 조사 조회 API (Read-only, opt-in)

- `GET /api/intelligence/feed` is registered in FastAPI but defaults to **503** without `MARKET_INTELLIGENCE_FEED_PATH`.
- The absolute path must point to an approved, already validated, locally available **public projection JSON** written by the Muse/Investment Intelligence OS publisher. The service does **not** fetch private GitHub or run agents.
- The server enforces schema v1, research-only, no BUY/PICK, blocks future data, strips unexpected candidate/event fields (portfolio/thesis/etc.), bounds file size 512KB and output events, adds ETag and 60-second Cache-Control.
- Muse must validate real source and as-of first. Even a valid JSON file is not proof of authentic data, audit, or a completed three-agent debate.
- In `chart-view-toss` the companion panel is **off by default**; enable `VITE_MARKET_INTELLIGENCE_ENABLED=1` after API staging, end-to-end validation and separate deployment approval. No existing `/api/home-bootstrap` or PICK history source has changed.
- Testing: `python -m unittest tests.test_intelligence_feed_service -v` plus backend regression and Toss `npm run qa:prepush`.
- Security: never point the env var to full Muse DB, private portfolio, personal analysis records or credentials; stage a sanitized derivative on backend filesystem, verify hash, then switch atomically. Run shadow tests before enabling. Default 503 is expected until Muse deployment.
