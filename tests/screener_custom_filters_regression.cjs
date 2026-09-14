// Regression: ISSUE-009 — Screener opened on an empty preset and lacked composable filters
// Found by /qa on 2026-09-15
// Report: .gstack/qa-reports/qa-report-chart-view-bsg6-onrender-com-2026-09-15.md
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('screener starts with all stocks and exposes composable direct conditions', () => {
  const js = fs.readFileSync('static/js/screener.js', 'utf8');
  assert.match(js, /let preset = 'all'/);
  assert.match(js, /let minValue = 0/);
  assert.match(js, /data-screen-preset="all">전체 보기/);
  for (const key of ['rsiMin', 'rsiMax', 'volumeMin', 'ret20Min', 'scoreMin', 'trend']) {
    assert.match(js, new RegExp(`data-screen-custom="${key}"`));
  }
  assert.match(js, /window\.__resetScreenerCustomFilters/);
  assert.match(js, /window\.__getScreenerCustomFilters/);
});
