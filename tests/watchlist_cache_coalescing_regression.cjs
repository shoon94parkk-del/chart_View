// Regression: ISSUE-008 — first watchlist entry repeated the same quote request
// Found by /qa on 2026-09-15
// Report: .gstack/qa-reports/qa-report-chart-view-bsg6-onrender-com-2026-09-15.md
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('watchlist paints fresh cached quotes and coalesces an in-flight refresh', () => {
  const js = fs.readFileSync('static/js/watchlist_v30.js', 'utf8');
  assert.match(js, /const QUOTE_FRESH_MS = 5 \* 60 \* 1000/);
  assert.match(js, /if \(!force && hasFreshQuotes\(rows\)\)/);
  assert.match(js, /if \(!force && quoteLoadPromise\) return quoteLoadPromise/);
  assert.match(js, /rows\.forEach\(\(row\) => applyQuote\(row\.symbol, quoteFor\(row\.symbol\), false\)\)/);
});
