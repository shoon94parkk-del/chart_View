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

test('heatmap uses market cap sizing and only promotes logos on genuinely large tiles', () => {
  assert.match(js, /relativeWeight/);
  assert.doesNotMatch(js, /Math\.pow\(cap,/);
  assert.match(js, /return Math\.max\(1, number\(row\.marketCap\) \|\| 1\)/);
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

test('template loads corrected rollback-safe heatmap assets', () => {
  assert.match(html, /\/static\/css\/home_heatmap_v57\.css\?v=20260922v59a/);
  assert.match(html, /\/static\/js\/home_heatmap_v57\.js\?v=20260922v59a/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(js, /HEATMAP_CACHE_KEY = 'chartview-home-heatmap-v59'/);
  assert.match(js, /박스 면적 = 같은 시장 내 실제 시가총액 비중/);
  assert.match(js, /rect\.height >= 0\.25/);
  assert.match(js, /stripNav\.hidden = next === 'heatmap'/);
  assert.match(js, /cvhm-empty/);
});
