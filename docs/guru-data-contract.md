# Guru reference screening contract

Period collection uses individual official major-account requests matching the full-account report's receipt and financial basis. A live trial of the official multiple-company API processed only 18 companies in 20 minutes versus 900 in the previous bounded run, so bulk prefetching was removed. The unused company-profile/fiscal-month request remains removed because a fiscal month does not establish an actual annual observation period. Two workers share the request/deadline/020 budget.

This is a new additive, cached analysis surface. The original technical screener and financial-history API remain unchanged.

`guru_screening.json` has schemaVersion 1, criteriaVersion cv-gurus-v2, snapshotVersion, price tradeDate, financialAsOf, and separate buffett/lynch/oneil/minervini/greenblatt strategies. Counts partition the unique KIND universe; evaluated=matched+failed. Pending, insufficient and unsupported are distinct. Only matched rows become candidates, sorted by name except Greenblatt's documented ascending annual-PER ranking. Original Buffett/Lynch math is unchanged.

`GET /api/guru-investing/{ticker}?version=...` reads checked-in evidence only. Different versions return 409; no provider I/O is performed. The evidence is published before its snapshot and both files must share the exact content version.

Buffett reference: last three annual net incomes >0; ROE each ≥10%, mean ≥15% using average total equity (four balance years); OCF each >0, cumulative OCF ≥income; latest total liabilities/equity ≤100%. This is not owner earnings or moat verification.

Lynch reference: positive basic common EPS in four consecutive years, historical CAGR 10–30%, latest EPS increased, annual reported EPS PE/historical CAGR ≤1, OCF >0 and liabilities/equity ≤100%. Annual PE is not TTM/forward PE. An unresolved corporate action excludes the per-share comparison. Criteria are Chart View's implementation choices, not a claim of an investor's exact rules or recommendation.

Collection uses the existing server-side DART key, 400-company/2400-request/1200-second default budgets, two workers with thread-local HTTP sessions and a shared locked request/deadline/020 stop budget, one network retry, and no auth/rate-limit retries. Up to two requests already in flight can finish after a stop signal. Corporate disclosures are scanned for per-share-changing events over the four-year observation interval; identified events remain unverified unless a consistent adjustment can be established. Missing values are never zero. CheckedAt remains distinct from filingDate and tradeDate.

Each bounded job commits progress and resumes missing companies before due rechecks. No provider request happens during Home, strategy selection or evidence expansion. Pricing rebuilds use a freshly fetched main to avoid publishing a stale close after a competing data commit. Initial partial scope is disclosed; a 14-company seed is never full-market coverage.

## v2 growth, trend and quality/value extension

See `guru-five-implementation-2026-10-05.md` for exact formulas and references. Daily bars are cached separately from original technical screening. The same-date verified-positive-close ordinary-company cohort must have >=90% valid253-session histories before publishing relative-return criteria. Full-universe missing quotes/history remain insufficient. Midrank handles ties, all comparisons use actual High/Low, previous55-session pivot and previous50-session volume exclude the breakout day. There is no proprietary IBD RS/RSI substitution.

Quarter collection selects only companies whose available annual necessary conditions pass. A definitive failed necessary condition is failed without extra provider requests, not a fabricated complete CAN SLIM assessment. A missing necessary quarter is pending; a checked incomplete/unverified source is insufficient. Direct full-account three-month EPS/revenue and prior-year same-quarter fields must match a receipt whose major-account Jan1–quarter-end period is verified. Cumulative weighted-average EPS is never subtracted; Q4 is insufficient until direct comparable EPS can be established.

Greenblatt uses explicit ROA/PER alternative and excludes financials/utilities. ROA=latest annual total income/year-end total assets, >=25%; dated annual common EPS PE5–20. Qualifying firms are ranked by ascending PE, tie symbol, up to30. This is not EBIT/EV or EBIT/tangible capital. Extra candidates beyond30 are counted failed selection, not insufficient/pending. Source/evidence carries the original accounts and prices. Necessary EPS/action/source freshness gates remain intact.

Additional bounded collection: market240sec, quarter400companies/1000DARTrequests/300sec; original annual limits remain unchanged. The workflow has35min job allowance. Data merges must preserve later quarter/price observations, rebind to latest main prices and atomically publish evidence then results. Stored period/raw rows permit independent arithmetic audit on another PC.
