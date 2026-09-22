const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const promo = fs.readFileSync('static/js/promo_v1.js', 'utf8');
const html = fs.readFileSync('templates/index.html', 'utf8');
const ux = fs.readFileSync('static/js/ux_v3.js', 'utf8');
const ledger = fs.readFileSync('static/js/ai_pick_ledger_v52.js', 'utf8');

test('share uses current public canonical and never the retired Render host', () => {
  assert.doesNotMatch(promo, /chart-view-bsg6\.onrender\.com/);
  assert.match(promo, /document\.querySelector\('link\[rel="canonical"\]'\)/);
  assert.match(promo, /chart-view-pkv8\.onrender\.com/);
  assert.match(html, /\/static\/js\/promo_v1\.js\?v=20260923v68/);
});

test('share URL preserves current app context', () => {
  assert.match(promo, /function currentShareRoute\(\)/);
  assert.match(promo, /route\.view = 'ai-picks'/);
  assert.match(promo, /url\.searchParams\.set\('tab', route\.tab\)/);
  assert.match(promo, /url\.searchParams\.set\('view', route\.view\)/);
  assert.match(promo, /url\.searchParams\.set\('symbol', route\.symbol\)/);
  assert.match(promo, /url\.searchParams\.set\('name', route\.name\)/);
  assert.match(promo, /version: 'v68'/);
});

test('receiver already supports PICK and stock-detail deep links', () => {
  assert.match(ux, /const requestedTab = params\?\.get\('tab'\)/);
  assert.match(ux, /view: params\?\.get\('view'\)/);
  assert.match(ux, /const symbol = String\(params\?\.get\('symbol'\)/);
  assert.match(ledger, /params\.get\('view'\) === 'ai-picks'/);
  assert.match(ledger, /openView\('ai-picks'\)/);
});
