const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('opening the chart resizes canvases after the hidden tab becomes visible', () => {
  const source = fs.readFileSync('static/js/ux_v3.js', 'utf8');

  assert.match(source, /function scheduleChartResize\(tabId\)/);
  assert.match(source, /requestAnimationFrame\(\(\) => \{\s*requestAnimationFrame\(\(\) => window\.dispatchEvent\(new Event\('resize'\)\)\);/);
  assert.match(source, /syncNavigation\(resolved\);\s*scheduleChartResize\(resolved\);/);
  assert.match(source, /syncNavigation\(tabId\);\s*scheduleChartResize\(tabId\);/);
});
