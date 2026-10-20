# Debate Archive API / Toss UI (opt-in)

GET /api/intelligence/debates is read-only, disabled (HTTP 503) until the operator explicitly sets **INTEL_DEBATE_FEED_PATH** to an absolute local JSON path.

Contract:
- schema_version 1, kind debate_archive, publication_status EXPLICITLY_APPROVED.
- generated_at timezone-aware ISO and debates[] (1..30).
- Each debate: id, date YYYY-MM-DD, company, ticker, topic, status COMPLETED/PARTIAL/BLOCKED, verdict BUY/WAIT/SELL/UNKNOWN, **audit_verified:false**, phases[].
- Each phase: role mer/nonggu/meng/other, stage context/phase1/attack/rebuttal/final/audit, title, text, source_path beginning records/debates/.
- Per-phase text <= 16,000 chars; max 24 phases/debate, 4 MiB document.
- Public projection enforced again on API. ETag, max-age 60.
- Historical verdict means *what the old markdown says*, **not** an audited or current PICK.

**Privacy critical:** Toss / Chart View API is public. Never read the private GitHub repo, personal records or VM database from public FastAPI requests. Only an owner-selected, manually reviewed archive projection may be placed on the API host. Repository debate files can contain prices/portfolio values or private text; raw archive publication is NOT authorized by code creation. Keep env unset and Toss feature flag off until the user approves the exact export. Review all content including free-form text; key scanning alone cannot detect private information inside prose.

Integration: Toss PR #141 (stacked on #140), build-time VITE_DEBATE_DASHBOARD_ENABLED=1 *only after* real approved API data is validated and deployment separately authorized. No automatic trades, no extra LLM calls on page load.


### Shadow progress API (optional)

GET /api/intelligence/shadow/status reads a separate INTEL_SHADOW_STATUS_PATH file. Default disabled, HTTP 503. The public file requires EXPLICITLY_APPROVED and only returns state NOT_STARTED/RUNNING/PAUSED/STOPPED, generated_at, period_started_at, last_execution_at, runs_total, screenings_total, debates_total, audits_approved, audits_blocked, failures_total. All counts are bounded integers and only aggregated observations are exposed; no symbols, investment amounts, personal information or raw logs. This API does not start a Shadow cron job. The frontend shows the report as STALE after 36 hours without a refreshed feed.

Historical smoke proof fields smoke_runs_total and smoke_audits_approved are counted separately from regular cron runs. They never change state to RUNNING and never start the fourteen-day period.
