const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('screener KPI counts use full-dataset preset counts, not only rendered rows', () => {
  const patterns = fs.readFileSync('static/js/ux_patterns_v12.js', 'utf8');
  const interactions = fs.readFileSync('static/js/ux_interactions_v13.js', 'utf8');
  const releaseUi = fs.readFileSync('static/js/release_ui_v40.js', 'utf8');
  assert.match(patterns, /data-screen-preset="volume"/);
  assert.match(interactions, /data-screen-preset="oversold"/);
  assert.match(patterns, /표시 종목 상승/);
  assert.match(patterns, /표시 평균 RSI/);
  assert.match(releaseUi, /activePreset\?\.querySelector\('span'\)/);
});
