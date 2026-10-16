# September DRAM MoM discrepancy

Status: 최초 조사는 미배포 상태였으며, 사용자 후속 승인으로 PR #153에 포함해 운영 배포했습니다. 최종 SHA와 운영 확인은 [PR #153 release 댓글](https://github.com/shoon94parkk-del/chart_View/pull/153)을 참조합니다. 아래 원인·초기 검증·당시 승인 범위 기록은 최초 조사 시점을 보존합니다.

## Reproduction and independent arithmetic

Read-only production requests on 2026-10-16 confirmed:

- `/health` revision: `1ee91ef2088854ce3c2d4c2cbac8dd09944ccd93`.
- `/api/export-momentum`: `period=itemPeriod=2026-09`, DRAM `exportsUsdBillion=16.777`, `exportMoM=-46.7`. Snapshot `updatedAt=2026-10-16T10:21:02.572569+09:00`.
- `/api/export-momentum/semiconductor-trends`: DRAM HSK `8542321010`, August `15.7331`, September `16.777` USD billion. The September amount and period agree with the overview.
- The existing Toss frontend displays the overview's `exportMoM` directly. Its twelve-month amount chart uses the independent trends history. Both use September, and the chart is an amount chart, not a weight/unit-value chart.

| Segment | August USD billion | September USD billion | Operating overview MoM | MoM implied by amount history |
| --- | ---: | ---: | ---: | ---: |
| DRAM | 15.7331 | 16.7770 | -46.7% | **+6.6%** |
| Flash memory | 2.8622 | 3.2968 | -42.4% | **+15.2%** |
| Memory MCP | 12.2253 | 15.0140 | -38.6% | **+22.8%** |

For DRAM, `(16.7770 / 15.7331 - 1) × 100 = 6.6351%`. Duplicating August gives `(16.7770 / (2 × 15.7331) - 1) × 100 = -46.6825%`, exactly the erroneous displayed percentage after rounding. These amounts are the public API's four-decimal USD-billion values, not an independently retrieved unrounded Customs XML record. This investigation establishes an internal calculation error, not a full audit of upstream trade statistics.

## Root cause and scope

Commit `0e85329e5bec8559d55ab9c7498260ac87415710` replaced the expensive previous-month full table with five targeted HSK queries. The broad memory query `854232` can return the same ten-digit DRAM/Flash/MCP rows that their individual queries return. `_fetch_semiconductor_previous_month_rows` concatenated them, and the generic exact-HSK selector summed both copies.

The combined previous-month amounts **and weights** were doubled for those three segments. Identical duplication of both cancels in unit-value MoM; that cancellation is not guaranteed for incomplete/conflicting responses. Current amounts, YoY, independent twelve-month history and the protected PICK/LAB paths do not use this combined comparator. Memory-total, SRAM and DRAM module remain unchanged in the reproduced identical-overlap controls.

Fix only the previous-month collector:

- Merge by normalized month and HS identity; keep distinct parent/child codes.
- Compare parsed export amount and weight, accepting equivalent date/HS/numeric representations and backfilling a missing field from a compatible duplicate.
- If two non-missing values disagree, omit the optional comparison batch rather than choose a completion-order-dependent value or form an incomplete rollup.
- Retain five parallel provider requests, optional query failure behavior, existing caches/TTLs/endpoints/formulas and generic signed aggregation. No additional provider source, full-table request or frontend correction formula.

The pre-existing possibility of an incomplete memory-total on a failed broad-prefix request with successful child requests is outside this duplicate fix. It is not represented as newly resolved.

## Regression validation

Use the repository's requirements plus pytest/httpx/yfinance, then:

```sh
python -m pytest -q tests/test_export_semiconductor_mom_dedup.py tests/test_export_momentum_service.py tests/test_export_signed_balance.py tests/test_export_error_redaction.py
python -m pytest -q
node --test tests/frontend.test.cjs tests/live_quotes_v56_contract.cjs tests/home_heatmap_v57_contract.cjs tests/macro_policy_v62_contract.cjs tests/server_live_cache_v66_contract.cjs tests/share_deeplink_v68_contract.cjs
python scripts/build_frontend_bundle.py --check
python scripts/build_boot_bundle.py --check
```

The new nine tests exercise collector → breakdown with overlapping prefix/exact responses, including the reported DRAM values. Before the fix, seven failed and two passed; the DRAM case reproduced `-46.7` instead of `+6.6`. After the fix, all nine and all 64 focused tests passed. Full Python: **780 passed**, with 79 existing Python3.12/Starlette deprecation warnings. Required Node contracts: **52 passed**. Both generated bundle freshness checks passed; no frontend bundle changed.

An independent read-only review found no blockers. It also passed the new/signed tests and eight forced forward/reverse completion-order checks without external provider calls.

Browser checks used the public deployed frontend assets with fixed captured JSON. The before case reproduced -46.7% at 390px; controlled **amount-only** corrected inputs displayed +6.6% alongside the unchanged August/September bars at Chromium 320/390/430px and iPhone WebKit emulation. All five checks passed with no page errors or viewport overflow. This replay validates amount presentation, not a released backend, unrounded weight correctness, all other API flows, or an official raw-data re-fetch. The unrelated country API was deliberately isolated with a test error response. Native Toss Sandbox was not run.

## Publication boundary

The branch starts at freshly fetched backend main `f0f0d3b4278460591770796c5849aa090f0f4517`. Only the collector, new regression tests and documentation change. No PICK selections/records/scores/states/performance, LAB core, investment strategy/formula, quote provider, frontend UI or infrastructure settings change.

This check does not authorize or perform another main merge/Render deployment. Operating responses can continue to show the old percentages until the tested change is explicitly released. Deployment verification must identify the exact tested main revision via `/health`, let the existing caches rebuild normally, and compare overview MoM with the same-HSK, same-month history again; a Render `live` label alone is insufficient.
