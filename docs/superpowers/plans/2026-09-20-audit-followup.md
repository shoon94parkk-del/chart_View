# ChartView audit follow-up

Goal: implement the approved P0/P1 audit without changing investment scoring.

- [x] Quote provenance: use quoteAsOf rather than chart endDate; retain raw close separate from adjusted return series. Test quote timestamp versus historical range.
- [x] Screener: derive statistics from filtered data, paginate 100 rows, reset pagination on filter changes; synchronize tab accessibility in navigation owner.
- [x] Detail: independently render compare/valuation/consensus, 15-second bounded requests, failed-source retry, preserve active tab, add five chart periods with stale-request guard. Hide comparison controls only during detail.
- [x] PICK: one owner for count title; exclude missing returns from aggregate.
- [x] News: reject provider-tag-only relation, retain directly evidenced company aliases or known sector terms.
- [x] Rebuild bundles and content-hash changed asset URLs; run Python suite, Node behavior checks, inspect deployed UI.

Review risks: old responses after navigation, missing quote date, null financial fields, partial failures, pagination after changing filters.

Validation: 137 pytest checks and 4 Node behavior tests passed. Deployment verification pending.
