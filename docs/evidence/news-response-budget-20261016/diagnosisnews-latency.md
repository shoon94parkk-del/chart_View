# Read-only diagnosis: operational personalized-news latency

2026-10-16. Scope: existing local backend/frontend source, recorded production smoke JSON/logs and harness. No application source changes, provider/network requests, browser runs, tests, commits, deployments or extra model calls. PICK/LAB is outside scope.

## Finding

There is a real timeout-budget mismatch. The frontend has a hard10s personalized-news deadline, while the backend has no whole-request deadline and waits for all per-symbol work. The backend's provider `timeout=7` does not include thread-pool or semaphore queue time and is not a seven-second total wall-clock guarantee. Thus the source permits a successful response after the browser has already aborted.

The captured11–21s measurements are **end-to-end Playwright API-transport relay durations**, not instrumented backend/provider service times. They prove that these responses missed the client budget, but do not identify the precise origin of the time. The source has concrete contention/amplification opportunities; actual attribution requires a later authorized correlated measurement.

## Recorded evidence

Source: `live/production-smoke/results.json`, backend revision recorded as `a406a4c074a086017363e2c99d677488ce8da55d` and frontend revision `ee6511364d9ec7c7ac52e4b355fc01d7c138a5b1`.

| Chromium320 request | Relay HTTP result | Relay duration |
|---|---:|---:|
| Samsung/Apple/NVIDIA |200|8.900s|
| Samsung |200|11.477s|
| Samsung |200|20.430s|
| Samsung |200|17.950s|
| Samsung/Apple/NVIDIA |200|19.826s|
| Samsung |200|20.799s|

All above use ordinary requests, no `force=true`. The requests reuse the same Samsung symbol/name (`005930.KS`/`삼성전자`). The320 run spans08:46:03–08:47:10UTC, shorter than the300s server TTL. Its browser network-failure records include `net::ERR_ABORTED`, and the news/chart-evidence check timed out waiting45s for a browser `response` event. The harness failure stack points to the **detail-news response wait**, before the standalone reader stage. A successful late API relay is not a successful browser delivery.

Later390 news relays range0.158–1.686s;430 range0.175–0.416s; WebKit range0.155–1.862s. The captured390/430/WebKit detail and reader payloads explicitly report all requested groups as `success`/`cache: hit`, with no provider errors. This confirms saved server-cache reuse in those later runs; it does not by itself prove that all earlier delay was cold-provider latency.

Important ambiguity: initial320's three-symbol response finishes in8.9s, then identical Samsung requests still take11–21s within the TTL. On one warmed, responsive process those should not require another provider call. Possible explanations include cache-hit thread-pool queueing, API transport/proxy queueing, deployment/process/cache boundaries, or event-loop/CPU scheduling. No per-request server/cache/provider timing was captured for320 and its late response bodies were not saved. Do not choose one explanation as established fact.

## Actual implementation and intentional limits

Backend `news_service_v37.py`:

- Lines27–32: per-process memory `NEWS_CACHE`, TTL300s; max20 symbols; global bounded provider semaphore4. The four-call provider cap and full20-symbol coverage are intentional existing safeguards.
- Lines213–221 and273–277: one `requests.get(..., timeout=7)` per actual NAVER/Finnhub lookup. A Requests scalar timeout applies to connect and socket-read waiting, not total download duration. DNS, repeated address attempts, redirects, chunk progress and scheduling can extend elapsed time. There is no explicit retry loop in these news functions.
- Lines316–336: cache key is uppercased `symbol|name`. The cache lookup occurs **inside the synchronous worker**, before an untimed semaphore acquisition. After waiting for the semaphore, the function does not recheck whether another request already populated that key.
- There is no per-key in-flight owner/coalescing. Overlapping Home, detail and relationship requests for one uncached key can each call the provider, compete for the same four permits, and publish separate results. Cache writes occur only when each worker finishes.
- Lines364–367: all per-symbol work is scheduled through `asyncio.to_thread` and awaited with unrestricted `asyncio.gather`. One queued/slow symbol delays every completed group. Even a fresh cache hit must first get a shared default-executor thread.
- `main.py:166`,952,1021,2357,2386,2404,2418 also use `asyncio.to_thread`; valuation-band warming is launched after startup (`main.py:605`). News therefore shares default executor capacity with unrelated work. Runtime executor size and actual contention were not observed in this pass.
- `relationship_evidence_service.py:254` reuses the same news helper/semaphore/cache; its endpoint already has a9s caller timeout (`:281–285`). Its worker can continue after the caller deadline, because Python thread cancellation does not stop blocking HTTP work.
- Current error-only public retry (`force=true`) preserves fresh success/no_news groups and existing internal full-force semantics. It fixes cached provider errors, not a wall-clock deadline or in-flight duplicate work. It did not cause these ordinary-request measurements.
- `Procfile` and `render.yaml` show one Uvicorn process command, without an explicit workers flag. That local configuration does not establish actual Render instance count, process lifetime or deployment routing during the captured run.

Frontend current release source `src/api.js:72` passes `timeoutMs:10000`, `retries:0`, server `force=true` only on explicit retry, client TTL60s and ready-response-only caching. `src/requestClient.js:31–37,67` races transport against a real deadline, aborts the Fetch signal, and rejects late results. It does not merely rely on the browser honoring cancellation. No automatic news-summary request occurs before expansion; summary generation is a separate route and is not the cause of this headline endpoint's source-level wait.

Harness `live/live-smoke.mjs:109–117` calls `route.fetch({timeout:60000})`, records its complete duration, then fulfills the document route. A document can abort at10s while that independent API transport returns200 later. The45s response waiter does not extend the product's10s deadline.

## Feasible minimum correction, if authorized

Preserve semaphore4, provider limits, existing cache owner/TTL/keys, ranking/relation receipts, internal full-force and public error-only retry. Increasing provider concurrency or adding warming calls would add load without resolving the missing deadline. Raising only the frontend timeout could permit longer waits but would not improve responsiveness or establish a bounded backend.

A narrowly scoped reliability correction can use the current news owner in three cooperating pieces:

1. Read fresh ordinary/error-only-retry cache hits before submitting blocking work to the shared executor. This makes warm cache delivery independent of a saturated unrelated thread queue. Keep cache-hit counters and all existing data semantics.
2. Add per-key in-flight coalescing at the existing canonical helper, with a cache recheck after waiting for provider capacity. Home/detail/relationship consumers should share one acquisition per key; preserve existing explicit full-force behavior. Do not create another data cache, change TTL, or fabricate freshness.
3. Give the personalized-news endpoint one absolute collection budget below the frontend10s deadline (for example8s, leaving transport margin). Return completed real groups immediately at budget expiration and mark remaining groups as explicit errors such as `provider_timeout`/pending-unavailable, never `no_news` or an empty success. Do not write caller-deadline placeholders into the canonical news cache. Preserve the in-flight owner to accept actual late results and let later callers join the same work instead of starting duplicate retries. A timed-out caller must not cancel another consumer or replace a newer valid result.

The response deadline bounds server collection wait, **not end-to-end transport latency or provider thread lifetime**. If the20s delay is mainly transport/proxy queuing, a server-only fix will not establish browser delivery under10s. The above controls are source-supported improvements, not a proven explanation or production performance claim.

If scope must be extremely small, start with the warm-cache fast path plus a synthetic held-default-executor regression; it directly addresses why a valid cache hit can wait. This alone does not bound a truly cold request or a20-symbol batch. An8s partial deadline alone is also incomplete: without coalescing, repeated retries can add work behind the same blocked provider semaphore.

## Required focused proof before implementation completion

No tests were run for this diagnosis. A future authorized patch should first reproduce with synthetic held workers/providers:

- Fresh success/no_news hit completes while the shared default executor is occupied; no provider call or TTL change.
- Concurrent same-key Home/detail callers perform one acquisition; distinct keys remain bounded by semaphore4.
- Mixed ready/slow groups return by the server budget with real ready rows and explicit timeout metadata; no false no_news and no dropped saved evidence.
- Late provider completion updates only its valid owner, cannot overwrite newer success, and a subsequent caller receives real cache data.
- Caller cancellation/deadline does not cancel a shared consumer or leak duplicate queued acquisitions.
- Public force retries only cached errors; internal force compatibility and ordinary cache hits remain covered by the existing news/relationship tests.
- Up to20 symbols retain complete group ordering/status accounting; no PICK/LAB or ranking changes.

Then correlate one actual authorized cold/warm test with request IDs and safe timings (endpoint entry, cache hit/miss, executor/semaphore wait, provider elapsed, response completion). Capture response body cache flags for the slow sample, distinguish direct API transport from the browser relay, and compare the same harness before/after. Do not log credentials, provider query tokens or exception URL strings. Root decides whether to implement under the user's performance request.
