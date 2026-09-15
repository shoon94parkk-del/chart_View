const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('AI ranking timeout remains recoverable without reporting an expected abort as an app error', () => {
  const widget = fs.readFileSync('static/js/ai_daily_widget.js', 'utf8');
  const template = fs.readFileSync('templates/index.html', 'utf8');

  assert.match(widget, /setTimeout\(\(\) => controller\.abort\(\), 10000\)/);
  assert.match(widget, /e\?\.name !== 'AbortError'/);
  assert.match(template, /ai_daily_widget\.js\?v=20260915v9/);
});
