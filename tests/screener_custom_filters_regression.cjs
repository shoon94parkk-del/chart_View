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
  assert.match(js, /data-screen-preset="all">[\s\S]{0,80}전체 보기/);
  for (const key of ['rsiMin', 'rsiMax', 'volumeMin', 'ret20Min', 'scoreMin', 'trend']) {
    assert.match(js, new RegExp(`data-screen-custom="${key}"`));
  }
  assert.match(js, /window\.__resetScreenerCustomFilters/);
  assert.match(js, /window\.__getScreenerCustomFilters/);
});

test('screener candidate threshold matches the 30-point data model', () => {
  const js = fs.readFileSync('static/js/screener.js', 'utf8');
  const rows = JSON.parse(fs.readFileSync('static/data/screener.json', 'utf8')).stocks;
  assert.match(js, /const SCORE_MAX = 30/);
  assert.match(js, /const CANDIDATE_SCORE_MIN = 22/);
  assert.match(js, /max="30"/);
  assert.doesNotMatch(js, /row\.score \|\| 0\) >= 55/);
  assert.ok(rows.some((row) => Number(row.score || 0) >= 22 && (row.rsi14 == null || row.rsi14 <= 65) && Number(row.volumeRatio || 0) >= 1.2));
});

test('preset counts stay pending until the screener payload is available', () => {
  const js = fs.readFileSync('static/js/screener.js', 'utf8');
  assert.match(js, /data-screen-preset-count>…</);
  assert.match(js, /function updatePresetCounts\(\)/);
  assert.match(js, /badge\.textContent = count\.toLocaleString/);
});
