const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const source = fs.readFileSync('static/js/screener.js', 'utf8');

test('screener revalidates cached payload against the latest trade date', () => {
  assert.match(source, /meta\?\.tradeDate/);
  assert.match(source, /String\(payload\.tradeDate\s*\|\|\s*''\)\s*===\s*expectedTradeDate/);
  assert.doesNotMatch(source, /if \(payload\) \{\s*render\(\);\s*return payload;\s*\}/);
});

test('screener checks freshness again when the app becomes visible', () => {
  assert.match(source, /visibilitychange/);
  assert.match(source, /pageshow/);
});
