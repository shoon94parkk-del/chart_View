// Regression: ISSUE-007 — chart controls can move before their click handler initializes
// Found by /qa on 2026-09-15
// Report: .gstack/qa-reports/qa-report-chart-view-bsg6-onrender-com-2026-09-15.md
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('custom date toggle does not require the detached legacy container', () => {
  const chart = fs.readFileSync('static/js/chart.js', 'utf8');
  const html = fs.readFileSync('templates/index.html', 'utf8');
  assert.doesNotMatch(chart, /if \(!dateSection \|\| !customDateToggle \|\| !customDateFields\) return/);
  assert.match(chart, /if \(!customDateToggle \|\| !customDateFields\) return/);
  assert.match(html, /chart\.js\?v=20260915v36/);
});
