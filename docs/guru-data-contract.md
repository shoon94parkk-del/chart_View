# Guru reference screening contract

Period collection uses the official [multiple-company major accounts API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019017), in batches of at most 100 companies for the required annual years. Each full-account report is fetched individually. Batch dates must match the stock, receipt and financial basis; missing or changed receipts fall back to single-company dates. Prefetching shares the collector's global request/deadline/020 budget. An unused company-profile/fiscal-month request is removed because a fiscal month does not establish a full annual observation period.

This is a new additive, cached analysis surface. The original technical screener and financial-history API remain unchanged.

`guru_screening.json` has schemaVersion 1, criteriaVersion cv-gurus-v1, snapshotVersion, price tradeDate, financialAsOf, and separate buffett/lynch strategies. Counts partition the unique KIND universe; evaluated=matched+failed. Pending, insufficient and unsupported are distinct. Only matched rows become candidates, sorted by name.

`GET /api/guru-investing/{ticker}?version=...` reads checked-in evidence only. Different versions return 409; no provider I/O is performed. The evidence is published before its snapshot and both files must share the exact content version.

Buffett reference: last three annual net incomes >0; ROE each ≥10%, mean ≥15% using average total equity (four balance years); OCF each >0, cumulative OCF ≥income; latest total liabilities/equity ≤100%. This is not owner earnings or moat verification.

Lynch reference: positive basic common EPS in four consecutive years, historical CAGR 10–30%, latest EPS increased, annual reported EPS PE/historical CAGR ≤1, OCF >0 and liabilities/equity ≤100%. Annual PE is not TTM/forward PE. An unresolved corporate action excludes the per-share comparison. Criteria are Chart View's implementation choices, not a claim of an investor's exact rules or recommendation.

Collection uses the existing server-side DART key, 400-company/2400-request/1200-second default budgets, sequential provider I/O, one network retry, no auth/rate-limit retries. Sequential requests stay below the approved concurrency ceiling of two. Corporate disclosures are scanned for per-share-changing events over the four-year observation interval; identified events remain unverified unless a consistent adjustment can be established. Missing values are never zero. CheckedAt remains distinct from filingDate and tradeDate.

Each bounded job commits progress and resumes missing companies before due rechecks. No provider request happens during Home, strategy selection or evidence expansion. Pricing rebuilds use a freshly fetched main to avoid publishing a stale close after a competing data commit. Initial partial scope is disclosed; a 14-company seed is never full-market coverage.
