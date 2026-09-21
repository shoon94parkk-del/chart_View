# Chart View agent rules

Chart View is improved incrementally. Do not rely on chat memory alone and do not silently undo a behavior that was intentionally fixed.

## Read before editing
1. `docs/project-memory.md`
2. `docs/regression-guardrails.md`
3. `docs/decision-log.md`
4. `docs/handover.md`
5. Tests nearest to the code you will change

## Required workflow
1. Search for prior work on the same behavior before editing.
2. Preserve current UX/data contracts unless the user explicitly requests a change.
3. Add or update a regression test for every behavioral bug fix.
4. If bundled frontend source changes, keep source, generated bundle, and content-hash asset key synchronized.
5. `python scripts/build_frontend_bundle.py --check` must stay green.
6. Run relevant Python/Node/mobile checks.
7. Deploy only the exact tested `main` revision.
8. Verify `/health` revision and production UI; Render "live" alone is not completion.
9. Append the decision to `docs/decision-log.md`. Update project memory/guardrails when the architecture or invariant changes.

## Production
- Web: https://chart-view-pkv8.onrender.com
- Toss frontend: https://chart-view-toss.onrender.com
- Toss normally uses the Web backend/API.
- `https://chart-view-bsg6.onrender.com` is legacy/suspended and must not be used for current verification.

## Never regress these principles
- Do not replace an incremental refresh with a full refresh.
- Do not label a historical close as realtime/current price.
- Do not let clean-root navigation restore an old tab.
- Do not blank a valid chart because a refresh failed.
- Do not deploy a frontend source change with a stale release bundle.
- Do not call work complete before exact-revision production verification.
