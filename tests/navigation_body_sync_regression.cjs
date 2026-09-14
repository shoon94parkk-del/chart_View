const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('app navigation owns tab body state before the legacy switcher is ready', () => {
  const source = fs.readFileSync('static/js/ux_v3.js', 'utf8');

  assert.match(source, /function activateTabBody\(tabId\)/);
  assert.match(source, /content\.classList\.toggle\('active', active\)/);
  assert.match(source, /content\.style\.display = active \? 'block' : 'none'/);
  assert.match(source, /callLegacySwitch\('home'\);\s*activateTabBody\('home'\);\s*syncNavigation\('home'\);/);
  assert.match(source, /callLegacySwitch\(resolved\);\s*activateTabBody\(resolved\);\s*syncNavigation\(resolved\);/);
});
