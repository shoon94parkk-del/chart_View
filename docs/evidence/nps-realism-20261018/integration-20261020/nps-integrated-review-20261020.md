# NPS realism integrated-source review — 2026-10-20

Read-only review of `github:shoon94parkk-del/chart-view-toss` and `github:shoon94parkk-del/chart_View`, branch `feat/nps-realism-v2`. Implementation and full QA are coordinated by the parent. This reviewer wrote only this report and made no provider requests, product edits, commits or deployment changes.

Reviewed uncommitted implementation over latest frontend main `1fd9b1a72d8c27c5a713371b882bd192745800b3` and backend main `1cab36ac25ee0167152fbe8217a243cd628cf93a`. Read repository AGENTS, relevant architecture/release/data invariants and the previous independent financial review at `/workspace/nps-realism-research/final-review.md`.

## Integration result so far

No outstanding P1/P2 found after reviewing the completed AGGG optional-comparison adjustment and actual Oct19 realism publication. Browser, full-test, exact-SHA CI and production verification remain the parent's responsibility.

- Latest target KOSPI display and ±0.5 percentage-point inverse targets are preserved. New copy labels the range as the index corresponding to target-share 20.3–21.3%, rather than a statistical confidence/error interval. `src/npsAllocationView.js:44–49` keeps the other assets' current estimates fixed only for this conditional inverse calculation; this does not freeze their daily revaluation.
- `npsFreshness` is byte-unchanged in the merged source against latest main: KST noon grace, expected prior common weekday, age warning and explicit “시장 데이터 갱신 지연” remain. Filing warnings and new monthly warnings coexist at `src/npsAllocationView.js:34–42`.
- The new monthly check does not auto-certify holdings, allocation baselines or CUSIP mapping. Future/malformed notice fails closed and preserves reviewed balance date. Same-price-version metadata is repainted through the existing publication path.
- Latest published-data API/fixture repairs, debate/Shadow routes and unrelated main features are preserved by ancestry; frontend product diff from latest main is limited to the three NPS model/view/style files. Backend implementation diff is NPS-only.
- Cash decomposition, flow principal/interest, derivative-like carry proxy and private-NAV scenario calculations match the independently reviewed prior implementation. No new double-income, double-FX or second rate-loss subtraction appeared in the integration diff. Published point estimates and user scenarios remain distinct.

## Independent commands executed

A Node import check loaded the exact latest-main calculator through `git show origin/main:src/npsAllocationModel.js`, alongside the actual new calculator. Both validators accepted all three saved summaries. The nine central fields weight/gap/adjustment/total/domestic/other/targetKospi/saaKospi/taaKospi matched with maximum absolute difference **0** for each:

| Publication | Price date | New calculator weight |
| --- | --- | --- |
| historical `b7275c018c527bcd` fixture | 2026-10-16 | 22.776530917046365% |
| realism `e93a82d9da4a54a8` fixture | 2026-10-16 | 22.573519278787384% |
| latest-main `fa14da10ba84ec87` | 2026-10-19 | 22.90142010965326% |

The third row is the old published model before the parent's fresh realism recollection. It is not a new-model current estimate. Full suites were deliberately not duplicated while parent QA is running.

## AGGG optional-comparison proposal review

Parent's fresh collection found missing 2026-10-19 AGGG.L close/adjustedClose; treating every comparison series as mandatory drove the common date back to Oct16, which correctly triggered the latest-publication overwrite guard. BNDW drives the central overseas-bond value; AGGG drives only a separately labelled comparison. Making **only AGGG** optional is consistent with the estimator and improves current central coverage without inventing data.

Required implementation invariants communicated to parent:

1. Optional fetch exceptions and missing/invalid marks must not abort the central 12-series collection.
2. AGGG comparison requires USD currency and positive finite raw/adjusted prices on the exact baseline and chosen current date; never use a prior-day mark or an inferred return.
3. Missing AGGG must not break observation construction or appear as a valid same-date source observation. Publish explicit unavailable status and null return.
4. Omit only its comparison case; preserve economic-case and all central validation. The current JS validator accepts a nonempty seven-case set.
5. Show that the AGGG comparison was omitted because matching-date data is missing. Availability metadata participates in the version hash so a later valid same-date comparison can publish a coherent new version.

## Low-priority documentation consistency

`summary.update.frequency/scheduleUTC` and the realism report's “하루1회” currently omit the newer 13:30/16:30 KST fallback attempts. Preserve the primary daily-close semantics and describe retries when the coordinator updates operational records. No calculation defect follows from this text.

## Source identity before optional adjustment

- `npsAllocationModel.js`: SHA256 `16838b8a81dc8c1dabbbd7a782612eb26cf0a060dc24bde6568c16bcd274168c`
- `npsAllocationView.js`: SHA256 `71dffff5e6b6f31b70265ed65fa448bf47967f68740704ddcb8a5cea808e9f51`
- `nps_pipeline.py`: SHA256 `4be9e6bcf0d36a04785d4f8fd32200269db251601a3f86a9c64784277d1e1a39`
- `realism.py`: SHA256 `b271c2f5ec2d4ae2424ab6b45d4dec7aa2a91a5b9f387c43fa6de0e78ddfb74a`


## Completed optional-comparison and actual-publication follow-up

Reviewed the final implementation after the parent reported collection completion. All five proposed invariants are present: `OPTIONAL_CORE` excludes only AGGG from the common-date intersection; `read_core_chart` preserves required fetch failures and captures only optional failures; `same_date_prices` checks exact endpoint dates/currency/positive finite raw and adjusted prices; observation JSON converts invalid nonfinite provider numbers to null; sources, metadata and UI explicitly identify unavailable comparison data. No stale AGGG observation is substituted.

The final source also retries a missing comparison on the same central market date and resumes ordinary skips after recovery. Read the added deterministic regressions for both equal cutoff and holiday cutoff, central input/result preservation, recovery version change, subsequent provider skip and refusal to replace a newer central price date. The existing last-valid-publication guard remains intact. Workflow source push includes `scripts/nps/**` and explicitly forces same-date model recalculation, while all three scheduled attempts remain. Retry description consistency noted above is now corrected in the generated metadata.

Independent execution after final collection:

- `python scripts/nps_pipeline.py --check` succeeded for actual snapshot **b28f01645e1db7eb**, price date **2026-10-19**, 546 directly valued rows.
- Both exact latest-main and current JS validators accepted the actual new summary and its 552-row matching detail; central nine-field maximum difference **0** between old/new calculators.
- New current JS produced weight **22.914799137600834%**, target-share gap **2.1147991376008335 percentage points**, fixed-total internal adjustment **−33.78235803806814 trillion KRW**, conditional target KOSPI **5095.878844663598**. These are model outputs, not observed current holdings/trades.
- Actual AGGG observation is USD and has a valid July31 baseline but null Oct19 close/adjustedClose. Metadata correctly reports `unavailable`, null return, Oct19 comparison date; seven remaining assumption cases validate. All central assets retain Oct19 prices/returns.
- Independently ran `node --test tests/npsRealism.test.mjs`: **9 passed, 0 failed/skipped**. Broader QA results are owned by the coordinator and were not independently rerun here.

No new financial/model or integration blocker found. Actual new holdings, daily internal trades, private NAV/distributions and executed hedge exposures remain unobserved and are disclosed as such. This is a source/model review and offline publication validation, not a claim of empirical accuracy improvement, native Toss release, full browser QA or production publication.

Final reviewed source SHA256:
- `npsAllocationModel.js`: `aaf9ac874446596cf716e3df42378b6c6210df53493724ed51588e36b8732897`
- `npsAllocationView.js`: `ace559035eac5d2c418bceee1b8991ba043da113ffaaf70f9aa5357d7d7e2566`
- `nps_pipeline.py`: `43ea0c8b67f58cfde753e469e42f1bb78b4eb83a8b74082d901e93bdcb19fa23`
- `realism.py`: `74c2903f6d06d2f03c24ad82ea5964de537fae5cd1d4614563d434907798d7b7`


## Python 3.11/3.12 numeric compatibility follow-up

Reviewed the exact CI failure log `/tmp/nps-backend-ci-failed-20261020.log` and deterministic numeric comparison `/tmp/nps-python311-numeric-diff.json`. The original publication check failed on exact canonical-JSON equality of assumption results, before the existing math-drift assertion mutated anything. Recomputed assumption case differences are limited to roughly **3.55e−15 percentage points** in weight/gap and **5.68e−14 trillion KRW** in adjustment. They are consistent with Python 3.12's improved floating-point summation. This is a validator portability defect, not a changed allocation or trade assumption.

The narrow fix in `check_publication.matches_assumptions` preserves dictionary keys, list length/order, string metadata and unavailable-case records exactly; rejects booleans/strings/nonfinite values in numeric-result positions; uses the existing calculation tolerance `rel_tol=1e−10, abs_tol=1e−9` for result numbers only; and keeps numeric patch parameter values **and types** exact. Missing or extra metadata cannot pass via the tolerance path. No financial calculator, source selection, snapshot data, version, UI or provider behavior changes in this fix.

Independently executed against the current patch:

- Python **3.11.17**: actual `b28f01645e1db7eb` publication `--check` passed; `tests/test_nps_realism.py -k offline_assumption_check`: **32 passed, 40 deselected** in 0.98s.
- Python **3.12.14**: the same actual publication `--check` passed; the same new checks: **32 passed, 40 deselected** in 1.49s.

The 32 cases exercise accepted last-bit result roundoff and rejected material result changes, NaN/infinities, bool/string values, missing/renamed/extra result fields, changed IDs/labels/kind/note, one-ULP economic patch changes, patch type/key changes, case deletion/reordering, invalid collection types, missing sensitivity and unavailable metadata tampering. Deselected cases are simply outside this focused reviewer run; coordinator owns the full-suite and refreshed CI gates.

No new P1/P2 found in the numeric compatibility fix. Final backend pipeline SHA256 after this fix: `84717d6b83d9cacd89e7fa4e7b7b53f63514077fe3c4c94848526bc34810ca9f`.
