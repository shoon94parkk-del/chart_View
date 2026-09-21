# Project registry

Last updated: 2026-09-22

This is the cross-project index for software projects developed iteratively with the user. Each active repository keeps its own durable memory. Before changing a project, open that repository and read its local `AGENTS.md` and `docs/` memory files.

| Project | Repository | Purpose | Durable memory |
|---|---|---|---|
| Chart View Web | `shoon94parkk-del/chart_View` | Main stock-analysis web app / shared backend | `AGENTS.md`, `docs/project-memory.md`, `docs/regression-guardrails.md`, `docs/decision-log.md` |
| Chart View Toss | `shoon94parkk-del/chart-view-toss` | Apps in Toss client using shared Chart View backend | same four-file memory system |
| Mileway | `shoon94parkk-del/mileway-award-monitor` | Korean Air public daily award-seat explorer + alerts | same four-file memory system |
| LOCAL_LLM | `shoon94parkk-del/LOCAL_LLM` | Local/company web-LLM agent + Memory/Knowledge | same four-file memory system |
| ZYGO-IPD | `shoon94parkk-del/ZYGO-IPD` | ZYGO XYZ/IPD engineering analysis | existing `AGENTS.md` + project memory/guardrails/decision log |
| Peligood Bid Radar | `shoon94parkk-del/peligood-bid-radar` | Broad bid/pre-spec opportunity radar | same four-file memory system + provenance validator |
| Footprint | `shoon94parkk-del/Footprint` | Public digital-footprint self-audit | same four-file memory system |

## Rule for future projects

When a new repository becomes an active iterative project, add it here and create:
- `AGENTS.md`
- `docs/project-memory.md`
- `docs/regression-guardrails.md`
- `docs/decision-log.md`
- a CI/test contract that verifies the critical memory/guardrail exists

The repository itself is the source of truth. Chat history may help reconstruct context, but it must not be the only place where important engineering decisions live.

## What belongs in project memory

Record:
- current production/deployment targets
- active architecture/ownership
- data semantics
- UX decisions the user intentionally adopted
- performance optimizations that must not be reverted
- privacy/security constraints
- known failure modes and their root causes
- exact regression tests/verification path
- unresolved follow-ups

## What belongs in decision log

For each high-risk change, capture:
1. Problem observed
2. Decision made
3. Why that decision was chosen
4. Regression protection / test
5. Deployment/operational implication when relevant

This turns repeated debugging into reusable engineering assets rather than one-off chat fixes.
