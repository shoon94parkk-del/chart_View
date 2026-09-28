# PICK monitor review input

`static/data/pick_monitor_reviews.json` is the researched evidence input for P1.

A review is only considered complete when it contains at least one verified source dated on or after the PICK date. The deterministic engine then derives the status:

- no valid completed evidence -> `PENDING_REVIEW`
- completed review with no verified negative evidence -> `KEEP`
- one non-major independent negative signal -> `WATCH`
- one major verified negative fact OR two independent negative signals -> `SELL_REVIEW`
- `EXIT` is never created by this engine; it requires explicit user confirmation

Price action and technical indicators may be recorded for context, but cannot create `WATCH` or `SELL_REVIEW` without fundamental evidence.
