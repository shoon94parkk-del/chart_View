# Optional macro forecast receipts — 2026-10-16

This is new optional behavior, independent of the six saved inflation histories and the original sixteen macro indicators. `inflation_release_service.py` reads the optional `static/data/macro_forecast_cache.json` once per saved-cache request. It never performs provider I/O. No data file, credential, provider client, or scheduled collection is enabled by this change. Missing configuration produces explicit `not_configured` coverage and leaves existing rates and legacy comparisons intact.

## Availability and rights

No provider key was issued during the onboarding review. Trading Economics, Finnhub and FMP require a real user email/login; entitled calendar access and public display/historical retention rights remain unverified. A key alone does not establish those rights. The detailed onboarding report is outside the product repository at `/workspace/research/moneytoring-implementation-20261016/api-onboarding/findings.md`.

The offline importer defaults to no values unless the operator explicitly supplies `--rights-confirmed` after verifying public display and historical retention rights. This flag records an operator decision; it does not verify a provider contract. There is no new workflow or environment setting to turn on. Do not import the synthetic test values or research-only values into the product cache.

## Saved schema

The root has `schemaVersion: 1`, `provider`, `status`, `checkedAt`, `forecasts`, and `comparisons`. Status is `not_configured`, `unavailable`, `ok`, or `partial`. The provider name identifies the intended adapter, not an active account or successful API call.

Every forecast receipt supplies:

- `seriesId`: exactly `cpi`, `core_cpi`, `ppi`, `core_ppi`, `pce`, or `core_pce`.
- `month`: explicit observation month `YYYY-MM`; `rate`: `yoy` or `mom`; `basis`: exact matching `NSA`/`SA`; `unit`: `%`.
- `expected`: finite JSON number, including zero; strings, booleans and nonfinite values are rejected by the reader.
- `source.forecastName` and a safe HTTPS `source.forecastUrl`.
- For `evidenceKind: provider_archive`, the actual timezone-bearing `retrievedAt` no later than now and `archive: {url, eventId, contentSha256}`. The archive URL must be safe HTTPS without credentials or any query string, event ID must be nonempty, and the digest must be 64 hexadecimal characters.

CPI/PPI YoY use NSA and MoM use SA. PCE/core PCE use SA for both rates. Receipts attach only to an existing supported series and a saved point month or its `asOf`; unrelated periods remain unavailable. Duplicate identities `(seriesId, month, rate, basis, unit)` within either collection are quarantined, including conflicting values, rather than selected opportunistically. Individually valid forecasts and comparisons sharing an identity must agree on expected value and forecast provenance (evidence kind, actual retrieval time, archive URL/event/hash, forecast source and any capture/publication timestamps); conflicting pairs are quarantined in both arrays. Invalid comparison evidence alone does not suppress an otherwise valid forecast.

Archive evidence can display a forecast retrieved after publication. Its retrieval time is never converted into a pre-release capture timestamp, and `LastUpdate` is never treated as forecast publication time. This evidence alone cannot produce a colored surprise comparison.

A comparison additionally supplies `actual`, `actualVintage: first_release`, a timezone-bearing `publishedAt`, and an official HTTPS `source.actualUrl` (BLS for CPI/PPI; BEA for PCE). Verified official publication metadata must exist in the saved point or matching latest row. Publication instants must match exactly; date-only publication metadata must match the receipt's New York date. Absent historical publication metadata is an evidence gap and suppresses only the comparison, leaving a valid archived forecast available. Out-of-range timezone conversions reject only the comparison. The release's New York month must follow the completed observation month, and a generic official homepage cannot serve as an actual release source. `source.actualName` is optional. The importer never generates these comparisons from vendor `Actual`, `Previous`, revised indices, or a current vintage. Operators must separately establish the original official actual receipt; frontend verification remains in force.

Absent/empty evidence kind and `captured_before`/`pre_release_capture` retain the legacy rule `forecastPublishedAt <= forecastCapturedAt < publishedAt <= now`. They cannot use post-release archive retrieval to bypass that rule. Existing row comparisons are preserved verbatim; optional receipts cannot replace an existing month/rate comparison.

Each supported row and the inflation packet receive `forecastCoverage: {status, provider, checkedAt, forecastCount, comparisonCount}`. Counts refer to accepted optional cache receipts, not unchanged legacy receipts. Invalid or duplicate receipts make the affected row/overall packet partial. A missing cache is `not_configured`; a malformed, oversize or unsupported-schema cache is `unavailable`. Decoder nesting failures, duplicate JSON field names and nonstandard nonfinite constants are rejected without preventing the saved inflation response.

## Trading Economics adapter and offline operation

The documented response contract is https://docs.tradingeconomics.com/economic_calendar/schema/ . Its documentation is not an authenticated CPI response or a display entitlement.

`scripts/macro_forecast_data.py` accepts raw JSON bytes plus an explicit operator-verified event mapping. The mapping is an object keyed by actual `CalendarID`/`CalendarId`, each value supplying `seriesId`, `rate`, and `basis`. There are no built-in event IDs, category heuristics, inferred series labels, or guessed CPI/PPI/PCE mappings. Conflicting ID aliases are rejected. A provider `ReferenceDate` must contain an actual ISO reference month/date; `Date` and release-month arithmetic never supply it. Future reference months beyond current UTC month are rejected by the adapter.

`ForecastValue` or `Forecast` supplies survey consensus; `TEForecast`/`TEForecastValue` never substitutes. The provider must explicitly declare `Unit: %`. The digest is computed from the exact imported provider bytes and all accepted receipts preserve their archive event ID and actual retrieval time. Missing consensus stays missing.

After rights, event IDs and units have been independently verified, an operator can import an already acquired licensed archive:

```sh
python scripts/macro_forecast_data.py \
  --input /secure/path/provider-calendar.json \
  --mapping /secure/path/verified-event-map.json \
  --archive-url 'https://authorized-provider.example/public-archive' \
  --retrieved-at 'ACTUAL_UTC_RETRIEVAL_TIMESTAMP' \
  --rights-confirmed
```

Use a query-free public evidence URL without any key or token. No public query parameters are currently allowlisted; authenticated API request URLs are never evidence links. The timestamp placeholder must be replaced with the actual acquisition time; do not backdate it. An invalid import fails before replacing an existing cache. Import/reader hard limits are 2 MB and 2,000 rows per collection. The optional `fetch_te_cache` API accepts only an explicitly injected transport; it ships no HTTP transport. Its caller must bound acquisition time/bytes, and the adapter checks the final byte/row limits again. Neither the service reader nor the CLI calls this helper.

## Validation

`tests/test_macro_forecast_data.py` covers archive evidence, zero, duplicates, mismatched period/basis/unit, late legacy captures, official publication timing, malformed types, bounds, rights gating, explicit mappings, ReferenceDate, aliases and missing survey consensus. Existing inflation tests continue to verify provider-free saved data and calendar behavior. No production cache numerics were introduced, and no product, strategy, PICK/LAB, Home, or frontend bundle source is changed.

## 최종 로컬 검증

전체 Python 회귀 **957 passed / 0 failed** (기존 경고 80개, 15.09초), `python scripts/build_frontend_bundle.py --check` exit 0. 독립 검토의 JSON 실패 격리·증거 URL·원발표 검증·충돌·극단 날짜 문제를 수정한 뒤 실행했다. 보호 소스/데이터의 기준 SHA 대비 동일성은 [validation.json](evidence/macro-forecast-20261016/validation.json)에 기록했다. PR CI 및 실제 배포 검증은 별도로 기록한다. 실제 키 발급/폼 제출 0건이며 이 변경은 민간 컨센서스를 활성화하지 않는다.
