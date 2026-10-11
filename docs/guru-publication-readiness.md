# Guru publication readiness

2026-10-11: U01/T2 follow-up. Source verification is implemented; the current production publication gap is not closed by this patch.

## Why the gap recurs

`update-guru-screening.yml` generates and commits `guru_screening.json` and `guru_evidence.json` together. `guru_snapshot.publish_snapshot` replaces evidence before results locally, and the Git commit contains both files. Toss reads the result from raw GitHub `main`; the evidence API reads the files in the deployed Render revision. A Git commit therefore exposes the new result before a manual Render deployment exposes its evidence. Local atomic replacement cannot make these two hosts publish atomically.

The existing Render hook is optional and currently documented as unconfigured. Successful collection is not evidence publication success. The no-hook workflow summary now says publication is pending manual exact-revision deployment. A hook request, if already configured, still requires verification. No hook, credential, service, provider recollection, runtime cache, or deployment mode is added.

## Existing release command now checks Guru

Use the tested checkout of the exact final `main` revision that includes the data. Manually deploy that revision using the existing Render service, then run:

```sh
APP_URL=https://chart-view-pkv8.onrender.com \
EXPECTED_SHA=<full-tested-main-sha> \
python scripts/verify_deployed_release.py --attempts 1 --output test-results/release-verification.json
```

`verify_deployed_release.py` retains the exact `/health` revision and asset checks and also requires:

1. Saved result and evidence metadata have the same version, criteria and trade date.
2. The deployed result and the public raw GitHub result both equal the tested result, including generation metadata and candidates.
3. All five strategies have valid coverage partitions and every saved candidate has matching saved strategy evidence.
4. Each strategy with candidates opens its first actual candidate through `/api/guru-investing/{symbol}?version=...`, and the response equals the saved evidence, including symbol, strategy, version and trade date. Shared candidates use one request.
5. A deliberately non-current version returns HTTP409 `snapshot_changed` and the expected current version. A missing/error response does not count as this protection passing.
6. Both result sources and the deployed revision still match after the checks.

The JSON artifact records `guru.strategies` with `evidence_verified`, `no_matches`, or `unavailable`, coverage counts and missing reasons. Empty/unavailable strategies do not borrow another strategy's candidate. If no strategy has candidates, the 409 probe is explicitly `not_checked_no_candidates`, never reported as verified. Missing strategy data fails verification.

Existing production CI calls this command before and after UI checks, so the readiness gate is part of the existing release verification path. Collection can remain successful while the manual publication is pending; a collection workflow's green status is not release readiness.

## Manual recovery and limitations

Before publishing, record the tested backend SHA, its result version and all five coverage states. Deploy that exact revision, run the command above, and retain its output plus Toss's actual candidate-evidence UI smoke. During the deployment boundary keep the existing frontend `409` handling and refusal to replace a newer result with an older server result.

If GitHub `main` advances to another Guru result during deployment or verification, the command fails rather than reporting the older backend ready. Test and publish the new final main revision using the same manual process. A bounded read cannot guarantee that a later collection will not advance raw `main`; ongoing synchronization still depends on the existing manual publication operation. This patch detects and documents the gap and prevents a false release-verification success. It does not eliminate the gap, select older CDN data, or fetch provider data at request time.

## Validation

Fifteen new deterministic release tests reproduced the missing gate before implementation. Target release/Guru tests: 46 passed. Full Python suite: 714 passed, five pre-existing dependency/deprecation warnings. Release and boot bundle freshness checks passed. Current source base: `86b790425d5348ee1bf5bead31a4e9af00ec8f84`.

Read-only production check at 2026-10-11 03:14:50 UTC: `/health.revision` was `ae06abd12405e4c76d33ee2a0653b9fa28780e8a`; backend result `a44945d27014caff69b5`, generated 2026-10-09; CDN result `ddc4483acdd78555148e`, generated 2026-10-11. Both use trade date 2026-10-08. CDN Buffett candidate `383220.KS` returned409 with backend's older version. No push, workflow dispatch, merge or deployment was performed for this source patch.
