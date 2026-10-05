# Five guru-reference strategies and portable handoff

Classification: user-approved new behavior, additive to the two existing screens.

- [x] Preserve Buffett/Lynch exact thresholds and dated quote/evidence contracts.
- [x] Deterministic O'Neil growth/breakout, Minervini trend and Greenblatt alternative rules with missing-data/boundary tests.
- [ ] Dated full-market OHLCV and necessary single-quarter EPS/revenue collection; no browser provider I/O.
- [ ] Compact five-strategy Toss navigation, criteria, distinct evidence and direct preview routes.
- [ ] Python/Node/build/mobile regression checks and independent real-data arithmetic.
- [ ] GitHub PRs, tested-main deployment and exact health/assets/evidence verification.
- [ ] Durable new-PC setup/runbook, decision logs, release limits and final verification record.

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
- OpenDART full single-company statements API documents `thstrm_amount` / `frmtrm_q_amount` three-month IS observations. Same-receipt major-account income periods establish the Jan1–quarter-end fiscal alignment. Weighted-average cumulative EPS is never differenced.

## Delivery gates

Checked-in cash/financial/quarter/bar caches contain no secret. The existing DART key stays in GitHub/Render secrets. Current Render manual deploy is authorized; do not transfer deploy-hook secrets to another service without the user's separate authorization. Native Android/iOS Sandbox and remaining public-launch/provider rights gates remain in the Toss release document.
