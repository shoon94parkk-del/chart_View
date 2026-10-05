# Five guru-reference strategies and portable handoff

Classification: user-approved new behavior, additive to the two existing screens.

- [x] Preserve Buffett/Lynch exact thresholds and dated quote/evidence contracts.
- [x] Deterministic O'Neil growth/breakout, Minervini trend and Greenblatt alternative rules with missing-data/boundary tests.
- [x] Dated full-market OHLCV and necessary single-quarter EPS/revenue collection; no browser provider I/O.
- [x] Compact five-strategy Toss navigation, criteria, distinct evidence and direct preview routes.
- [x] Python/Node/build/mobile regression checks and independent real-data arithmetic.
- [x] GitHub PRs, tested-main deployment and exact health/assets/evidence verification.
- [x] Durable new-PC setup/runbook, decision logs, release limits and verification record.

## Scope and explicit adaptations

Buffett/Lynch v1 mathematics stays unchanged under the versioned v2 five-strategy snapshot.
O'Neil is a quantifiable subset of CAN SLIM: positive comparable four-year common EPS with each of the last three increases >=25%, latest total-equity ROE >=17%, latest due single-quarter EPS/revenue YoY >=25%, 252-session return midrank >=80, a last-five-session close above its preceding 55-session HIGH with volume >=1.4x preceding 50 sessions, current close 0–5% above that breakout line. New products, institutional sponsorship, valid chart bases and market direction are not assessed. No cumulative EPS subtraction.
Minervini: close >SMA50 >SMA150 >SMA200, SMA200 above its value 20 sessions earlier, close >=1.30x252-session LOW and >=.75x252-session HIGH, relative-return midrank >=70. VCP/entry/exit/risk sizing and fundamentals are not assessed. RS is not RSI or proprietary IBD RS Rating.
Greenblatt uses the publicly documented ROA/PER alternative: latest annual net income / year-end total assets >=25%, annual EPS PER5–20, positive verified comparable common EPS, financial/utility exclusions, lowest-PER first up to30. This is NOT EBIT/EV or EBIT/tangible-capital Magic Formula. No debt, preferred equity or excess cash is guessed. Existing assets/EPS permit immediate actual results.

## Source references

- IBD publisher's [20 Rules](https://shop.investors.com/images/promotional/20-Rules_102808.pdf) describes annual/quarterly earnings, sales and profitability; numerical breakout adaptation above is Chart View's own.
- Minervini's own [published workshop description](https://www.minervini.com/1MTPreview.pdf) describes trend/high-relative-strength/high-area principles; Chart View explicitly defines its own computable thresholds.
- AAII's [original description of alternate screening](https://www.aaii.com/journal/article/the-magic-formula-approach-to-stockpicking) lists ROA and low-PER substitution and warns about PER below5.
- [Magic Formula official FAQ](https://magicformulainvesting.com/Home/Faqs) describes quality/value and financial/utility exclusions.
- [OpenDART full single-company statements API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020) documents `thstrm_amount` / `frmtrm_q_amount` three-month IS observations. Same-receipt major-account income periods establish the Jan1–quarter-end fiscal alignment. Weighted-average cumulative EPS is never differenced.

## Delivery gates

Checked-in cash/financial/quarter/bar caches contain no secret. The existing DART key stays in GitHub/Render secrets. Current Render manual deploy is authorized; do not transfer deploy-hook secrets to another service without the user's separate authorization. Native Android/iOS Sandbox and remaining public-launch/provider rights gates remain in the Toss release document.

## Verified delivery checkpoint — 2026-10-05 KST

Implementation PRs: [Toss #110](https://github.com/shoon94parkk-del/chart-view-toss/pull/110), [backend #128](https://github.com/shoon94parkk-del/chart_View/pull/128). Necessary quarterly collection [run 37320207203](https://github.com/shoon94parkk-del/chart_View/actions/runs/37320207203) completed with 9 companies, 18 requests, zero provider errors. Seven reports supplied comparable actual 2026Q2 values; two remain insufficient. All quarter-collection pending counts are zero. Data commit `182cbdf7581a1fb41d4c2edf80e6fa8554fe3479`, snapshot `ca7bc07a7c3d4b261df3`, dated close **2026-10-02**.

| Method | Matched | Evaluated | Insufficient | Unsupported |
|---|---:|---:|---:|---:|
| Buffett | 54 | 1950 | 473 | 229 |
| Lynch | 37 | 1185 | 1238 | 229 |
| O'Neil subset | 0 | 1123 | 1300 | 229 |
| Minervini trend | 80 | 2050 | 373 | 229 |
| Greenblatt ROA/PER alternative | 3 | 1429 | 949 | 274 |

Every method partitions all 2652 universe records. Relative-strength coverage is 2050/2253 same-date positive-close supported ordinary companies (91.0%). This does not mean all 2652 have complete financial/history data. Unsupported, missing and failed criteria remain distinct.

Independent arithmetic re-read source observations, without invoking rule functions: all 80 Minervini matches' 50/150/200-day averages, previous-200-day average, high/low and 252-return midrank; all three Greenblatt matches' annual ROA/PER and order; seven actual quarter EPS/revenue source fields. Two growth-passing quarters still lack the required last-five-session volume breakout; hence zero O'Neil matches is a verified result, not an unfinished tab. The insufficient reports were not synthesized.

Validation: 448 Python tests, shared Web release-bundle check, 246 Toss Node tests, production build/26 exported routes, five-method fixture flows at320/390/430px including recovery, filters, sources and Back/Reload. Production source/data checkpoint passed `/health` revision, three Web canonical asset hashes and twelve actual matched-company API200/stale-version409 checks. Toss commit `92c3f030f446760fa984a76805fe550dd1fdd1a1` deployed as `dep-db1qn03tqb8s73ean140`; all35 static asset hashes and five direct routes matched the clean canonical build. Backend checkpoint `182cbdf` deployed as `dep-db1qr3psrm7s73ctf3l0`.

Actual narrow-screen checking found a wrapped Lynch caption making a91px row; [Toss #111](https://github.com/shoon94parkk-del/chart-view-toss/pull/111) shortens captions and strengthens all five row-height checks, without changing calculations. Its final live revision and CI are recorded in that PR/Render deployment history. The machine-readable [checkpoint evidence](evidence/guru-five-2026-10-05.json) is historical verification, not today's live prices or a claim that subsequent revisions are deployed.

New-PC entry points: this repository's [CODEX_HANDOFF](CODEX_HANDOFF.md) and [Toss CODEX_HANDOFF](https://github.com/shoon94parkk-del/chart-view-toss/blob/main/docs/CODEX_HANDOFF.md). Clone both latest main branches and start with AGENTS.md. Daily automatic backend publication, actual native Toss devices and public-launch gates remain explicitly separate.
