// Regression: chart time scale was calculated while the analysis tab was hidden.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('first chart reveal resizes and refits the hidden chart time scale', () => {
  const widget = fs.readFileSync('static/js/ai_daily_widget.js', 'utf8');
  assert.match(widget, /function installChartVisibilityFix\(\)/);
  assert.match(widget, /new ResizeObserver/);
  assert.match(widget, /tabObserver\.observe/);
  assert.match(widget, /chart\.resize\(width, 260\)/);
  assert.match(widget, /chart\.timeScale\(\)\.fitContent\(\)/);
  assert.match(widget, /setTimeout\(\(\) => refit\(true\), 120\)/);
});
