# Scheduled memory price collection implementation

> **For agentic workers:** Use superpowers:executing-plans or superpowers:subagent-driven-development task by task.

Goal: unattended public-latest collection with durable history and production publication independent of visits/deploys.
Spec: docs/superpowers/specs/2026-11-10-scheduled-memory-prices-design.md

Constraints: preserve memory APIv2/legacy alias,365source-date limit, public-latest only, actual source dates/units, missing versus0, no new paid service/credentials, no unrelated quote/Home/UI change.

## Task1 — durable collector
- [ ] TDD pure validation/merge in memory_price_publication.py, imports existing catalog/history helper from memory_spot_service.
- [ ] scripts/collect_memory_prices.py with --output(defaultstatic/data/memory_prices.json), optional --seed-history JSON for initial existing observations, validate-before-write and atomic replacement.
- [ ] Daily19:35/20:35KST workflow with dispatch, minimal deps, independent execution, contentswrite, serialized memory publication and bounded nonforce push retries. Data commit `[skip render]`.
- [ ] Test same-date merge, backward data, strict schema, partial/all-source failures, file preservation and schedule shape.

## Task2 — existing publication/API integration
- [ ] Extend published_data allowlist/strict validator and monotonic cache retention only for this new snapshot.
- [ ] Prefer validated published snapshot in memory endpoint, merge full stored history before optionalRedis/currentprocess history; preserve old bounded fallback if publication is unavailable.
- [ ] Normalize harmless whitespace in existing provider item labels and test actual GDDR double spaces.
- [ ] Add API/publication/empty Redis/old CDN regressions. No frontend source change; existing bundle check staysgreen.

## Task3 — release and evidence
- [ ] Seed current real API history and collect actual public latest; inspect all5groups/15items.
- [ ] Independent review, Python/frontend/bundle checks and CI; merge exact tested source and deploy existing backend service.
- [ ] Enable schedule through default-branch workflow; run it once, verify durable commit and real API adoption without another deployment.
- [ ] Record schedule, exact revision, runtime provenance, limits, and distinguish manual run from future schedule-triggered runs.
