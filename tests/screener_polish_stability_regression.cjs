// Regression: ISSUE-010 — Screener polishing retriggered its MutationObserver forever
// Found by /qa on 2026-09-15
// Report: .gstack/qa-reports/qa-report-chart-view-bsg6-onrender-com-2026-09-15.md
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('screener result polishing only writes when content changed', () => {
  const js = fs.readFileSync('static/js/release_ui_v40.js', 'utf8');
  assert.match(js, /if \(button\.textContent !== label\) button\.textContent = label/);
  assert.match(js, /if \(button\.getAttribute\('aria-label'\) !== aria\) button\.setAttribute\('aria-label', aria\)/);
});
