// Regression: ISSUE-007 — moved chart date fields stayed hidden after opening
// Found by /qa on 2026-09-15
// Report: .gstack/qa-reports/qa-report-chart-view-bsg6-onrender-com-2026-09-15.md
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('custom chart dates open in the container that owns the moved controls', () => {
  const chart = fs.readFileSync('static/js/chart.js', 'utf8');
  const css = fs.readFileSync('static/css/comparison_ui_v40.css', 'utf8');
  assert.match(chart, /customDateToggle\.closest\('\.v40-chart-periods'\) \|\| dateSection/);
  assert.match(css, /\.v40-chart-periods\.custom-range-open #custom-date-fields\s*\{[^}]*display:\s*grid\s*!important/s);
});
