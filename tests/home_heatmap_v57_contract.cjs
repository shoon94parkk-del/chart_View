const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const js = fs.readFileSync(path.join(ROOT, 'static/js/home_heatmap_v57.js'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'static/css/home_heatmap_v57.css'), 'utf8');
const html = fs.readFileSync(path.join(ROOT, 'templates/index.html'), 'utf8');
const main = fs.readFileSync(path.join(ROOT, 'main.py'), 'utf8');
const generator = fs.readFileSync(path.join(ROOT, 'scripts/generate_home_snapshot.py'), 'utf8');

test('heatmap is additive and does not block Home with historical calls', () => {
  assert.match(js, /requestIdleCallback/);
  assert.match(js, /\/api\/heatmap/);
  assert.doesNotMatch(js, /\/api\/compare/);
  assert.doesNotMatch(js, /location\.reload/);
  assert.match(js, /REFRESH_MS\s*=\s*60_000/);
  assert.match(js, /document\.visibilityState !== 'visible'/);
});

test('heatmap keeps U.S. true-cap sizing and only compresses Korea', () => {
  assert.match(js, /relativeWeight/);
  assert.match(js, /row\.market === 'KR' \? Math\.pow\(cap, 0\.82\) : cap/);
  assert.match(js, /미국 = 실제 시총 비중 · 한국 = 시총 영향 완화/);
  assert.match(js, /KRW 시총 기준 · 시인성 보정/);
  assert.match(js, /USD 실제 시총 비중/);
  assert.match(js, /area >= LOGO_AREA_THRESHOLD/);
  assert.match(js, /rect\.width >= LOGO_MIN_WIDTH/);
  assert.match(js, /rect\.height >= LOGO_MIN_HEIGHT/);
  assert.match(js, /row\.market === market/);
  assert.match(css, /grid-template-columns:minmax\(0,\.9fr\) minmax\(0,1\.1fr\)/);
  assert.match(css, /@media\(max-width:720px\)/);
  assert.match(css, /cvhm-name-row/);
  assert.doesNotMatch(css, /cvhm-logo\{position:absolute/);
});

test('server heatmap reuses shared Home SWR cache and preserves last valid market cap', () => {
  const start = main.indexOf('@app.get("/api/heatmap")');
  const end = main.indexOf('def compute_net_liquidity', start);
  const block = main.slice(start, end);
  assert.match(block, /await home_snapshot\(fresh=fresh\)/);
  assert.doesNotMatch(block, /fetch_quote_snapshot/);
  assert.match(main, /"207940\.KS"/);
  assert.match(main, /"AMZN"/);
  assert.match(main, /"TSM"/);
  assert.match(main, /row\.get\("marketCap"\) or \(previous_rows\.get\(ticker\) or \{\}\)\.get\("marketCap"\) or 0/);
});

test('persistent snapshot uses real valuation market cap, not trading volume', () => {
  assert.match(generator, /VALUATION_CACHE/);
  assert.match(generator, /MARKET_CAPS\.get\(ticker, 0\)/);
  assert.doesNotMatch(generator, /"marketCap": meta\.get\("regularMarketVolume"\)/);
});

test('template loads V60 rollback-safe heatmap assets', () => {
  assert.match(html, /\/static\/css\/home_heatmap_v57\.css\?v=20260922v60a/);
  assert.match(html, /\/static\/js\/home_heatmap_v57\.js\?v=20260922v60a/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(js, /HEATMAP_CACHE_KEY = 'chartview-home-heatmap-v60'/);
  assert.match(js, /version: 'v60'/);
  assert.match(js, /rect\.height >= 0\.25/);
  assert.match(js, /stripNav\.hidden = next === 'heatmap'/);
  assert.match(js, /cvhm-empty/);
});
