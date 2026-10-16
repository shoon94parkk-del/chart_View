# Public news response budget design review

Initial design verdict: **compatible with the approved scope**, pending implementation review. The observed relay times support an application-level deadline and queue-independent cache access; they do not isolate provider latency or establish an end-to-end network guarantee.

Reviewed `news-response-budget-brief.md` and base news service in `/workspace/chartview-news-response-budget-20261016`. No source edits, git commands, tests, browser actions, or provider I/O performed. Root and implementer received the following concrete design risks before implementation settled.

## Required implementation properties

1. **Real worker ownership survives the caller.** Do not remove the keyed owner when an asyncio waiter is canceled by the seven-second budget or a disconnected caller. An underlying thread may still be acquiring the provider semaphore or reading the provider response. Removing its owner early allows the next request to launch a duplicate. Shared queued work must also survive one waiter's cancellation; avoid propagating cancellation through an asyncio wrapper into its shared underlying future.
2. **Fresh cache reads precede dispatch.** Healthy cached groups and ordinary cached errors must return directly from the public request path, without entering a saturated worker executor. The public force flag bypasses cached errors only. Recheck fresh cache while handing off owner creation, so a previous owner's completion/removal cannot race into an unnecessary new acquisition.
3. **One application budget covers the whole collection.** Use one monotonic seven-second budget, collect every completed result, and retain requested symbol order. Sequential per-symbol seven-second waits, or waiting for pending-task cancellation/cleanup before returning, can exceed the approved collection budget. Deadline/busy placeholders must remain explicit error groups and never reach the cache.
4. **The 64-owner bound includes queued and running work.** An owner that has outlived its response still consumes capacity until actual completion. Check the cache before reporting capacity overflow. After completion, clear the same owner's slot, allowing future requests to proceed. Upstream provider concurrency remains four, including interaction with existing internal callers.
5. **Completion callbacks must not deadlock owner creation.** Adding a callback to an already-completed future can invoke it synchronously. Registering a callback that reacquires a non-reentrant owner lock while that lock is held can deadlock the endpoint. Cleanup should also be conditional on the registry still containing that exact owner.
6. **Keep public and internal force behavior distinct.** Public explicit retries coalesce failed groups and preserve healthy cache hits. Relationship-evidence internal `_cached_fetch(force=True)` continues its existing full refresh. Provider selection, ranking, relation receipts, item limits, TTL, and PICK/LAB behavior stay outside this change.

Requested regression coverage matches the brief: cache hits independent of the worker queue, concurrent normalized-key coalescing, one canceled waiter with another still waiting, timeout followed by real late cache completion, partial healthy results with explicit timeout errors, no placeholder cache poisoning, owner capacity/recovery, and public error-only versus internal full-force compatibility.

Implementation/final SPEC and QUALITY disposition will be appended after the owner supplies the patch and evidence. End-to-end relay/network latency and exact-revision operational checks remain coordinator responsibilities.

## Implementation review, first pass

Read current service implementation and all new `tests/test_news_response_budget.py` cases. Reviewed `news-budget-green.txt`: **43 focused tests passed**, with the existing Starlette deprecation warning. Reviewer did not run tests or git commands.

The implemented public collection uses a module-owned `concurrent.futures.Future` per normalized symbol/name. Per-loop wrappers are shielded, so canceling a caller's wrapper does not cancel the real owner. The real worker publishes and removes itself after completion; cache checks run directly on the endpoint path and again under the owner handoff lock, before capacity rejection. Queued/running work consumes the 64-owner budget. Registry publication does not register a same-lock completion callback. Existing provider semaphore capacity remains four.

The endpoint creates one monotonic deadline before collection, waits once for available results, keeps requested symbol order, and returns explicit `news_timeout`/`news_busy` errors without caching these placeholders. Genuine late worker completion still writes the original cache. Validation rejects malformed cache/worker containers; existing error-only retry and ordinary cached-error reuse tests remain in the focused suite. New tests cover saturation, partial results, cancellation/coalescing, capacity and recovery, late completion, malformed containers, cross-loop sharing, and old public owner versus newer internal refresh.

The shared default executor is retained deliberately. The live-server coroutine deadline does not require waiting for provider threads, while a whole event-loop shutdown via `asyncio.run` can still wait for its default executor's real threads. Tests release held providers while the loop remains alive. This is compatible with an application response budget and is not an end-to-end network latency guarantee.

One internal-force compatibility issue was identified by the coordinator and confirmed in review: the generation guard currently returns newer canonical cached data to an older `force=True` caller, even though that caller acquired its own provider result. Generation ordering should prevent the older canonical cache write while preserving each internal force caller's own result and `cache: miss`. The ordinary public owner may safely return newer canonical data. Final SPEC/QUALITY disposition is pending this narrow fix and its two-force-caller regression.

## Final implementation disposition

**SPEC: PASS. QUALITY: PASS. No remaining Critical, Important, or minor findings in this scoped review.** This supersedes the pending disposition above.

The internal-force correction returns each forced caller's own actual acquisition with `cache: miss` while preserving the newer canonical cache generation. Reviewed the new two-forced-caller regression, which holds the first acquisition, completes the second, and verifies both distinct caller results plus the unchanged newer cache. The ordinary/public late-owner generation protection remains intact.

Reviewed final focused evidence: **44 passed**, one existing Starlette warning, in `news-budget-green.txt`. Reviewed full-suite evidence: **975 passed, 80 existing warnings**, in `news-budget-full.txt`; owner also reports a successful frontend bundle freshness check in the silent `news-budget-bundle.txt` artifact. Reviewer did not rerun any tests. The final documented contract in `docs/NEWS_RESPONSE_BUDGET_2026-10-16.md` accurately separates the application collection budget from relay/network latency and blocking-thread lifetime, and describes the cache, capacity, cancellation, singleflight and internal-force boundaries.

The source and meaningful concurrency regressions support the approved behavior: healthy cache groups bypass worker queues; public duplicate keys share one bounded real owner; late work retains ownership and fills the cache; partial timeout/busy groups are explicit errors and never canonical cache entries; provider concurrency remains four; newer completed cache generations remain protected; internal force results preserve their original caller identity. No provider selection, ranking, relation scoring, frontend source or PICK/LAB change was identified.

Remaining release work belongs to the coordinator: CI/integration, publishing and exact-backend-revision verification, and a same-harness production comparison. PASS makes no guaranteed end-to-end latency or provider-only speedup claim. No source edits, git commands, tests, browser actions, provider I/O or subagents were performed by this reviewer.
