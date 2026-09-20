# P0 release verification recovery

## Problem

The September 20 release had a passing API smoke but a failed mobile detail
layout check and a stale provider assertion. The bundle workflow then pushed a
second commit, so source checks and deployment could refer to different SHAs.

## Changes

- Commit source, generated JS/CSS, and content-addressed asset URLs together.
  `python scripts/build_frontend_bundle.py` prepares a change; `--check` validates
  it without modifying files. CI no longer pushes generated follow-up commits.
- Run all five mobile suites independently with `fail-fast: false`. Preserve
  their logs/artifacts even when a different suite fails.
- Verify `/health` revision, served HTML asset references and SHA-256 of the
  release JS/CSS and PICK widget before and after production UI checks.
- Permit the approved Korean index providers without accepting unknown sources,
  invalid prices, missing quote timestamps or absent freshness flags.
- Keep quote metadata accessible in a disclosure and explicitly place price and
  metrics on the same mobile grid row. Empty loading status no longer occupies
  a grid cell. Preserve the 420px chart position requirement and 44px controls.
- Account for progressive rendering in the existing detail test; save layout
  evidence before asserting and collect failures across scenarios.

## Validation and handoff

The working change passed 146 Python tests and 9 focused Node tests locally.
PR mobile checks and exact-revision production verification remain required
before this work can be described as deployed and complete.

For future frontend changes, regenerate the bundle before committing. Stale
generated files or asset keys deliberately fail CI. Keep Render's current
Git-backed deployment configuration; no extra paid service is required.

P1/P2 product changes (chart date formatting, news quality, screener redesign,
PICK statistics, observer performance work) are outside this P0 change, except
the mobile detail layout needed to restore the release gate.
