const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('condition reset clears quick filters and selects the unfiltered preset', () => {
  const source = fs.readFileSync('static/js/release_ui_v40.js', 'utf8');

  assert.match(source, /__setScreenerQuickFilter\('none'\)/);
  assert.match(source, /data-screen-market="ALL"/);
  assert.match(source, /data-screen-preset="all"/);
  assert.doesNotMatch(source, /data-v40-reset[\s\S]{0,900}data-screen-preset="candidate"/);
});

test('condition reset has an accessible name and an app-styled control', () => {
  const source = fs.readFileSync('static/js/release_ui_v40.js', 'utf8');
  const css = fs.readFileSync('static/css/release_ui_v40.css', 'utf8');

  assert.match(source, /aria-label="모든 검색 조건 지우기"/);
  assert.match(css, /\[data-v40-reset\]/);
  assert.match(css, /focus-visible/);
});
