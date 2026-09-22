const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const live = fs.readFileSync(path.join(ROOT, 'static/js/live_quotes_v56.js'), 'utf8');
const html = fs.readFileSync(path.join(ROOT, 'templates/index.html'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'static/css/live_quotes_v56.css'), 'utf8');

test('live quote layer only refreshes lightweight current quotes', () => {
  assert.match(live, /WATCHLIST_POLL_MS\s*=\s*5000/);
  assert.match(live, /\/api\/quotes\?tickers=/);
  assert.doesNotMatch(live, /\/api\/compare/);
  assert.doesNotMatch(live, /location\.reload|window\.__renderWatchlist/);
});

test('watchlist entry bootstraps all current quotes, then frequent polling stays visible-only', () => {
  assert.match(live, /document\.visibilityState !== 'visible'/);
  assert.match(live, /function activeMode\(\)/);
  assert.match(live, /visibleWatchSymbols/);
  assert.match(live, /fullWatchlist \? rows\.map\(\(row\) => row\.symbol\) : visibleWatchSymbols\(rows\)/);
  assert.match(live, /const bootstrapAll = modeChanged && mode === 'watchlist'/);
  assert.match(live, /fullWatchlist: bootstrapAll/);
  assert.match(live, /if \(inFlight\) inFlight\.abort\(\)/);
});

test('live quote cache merge preserves historical return fields', () => {
  assert.match(live, /safe\.quotes\[symbol\] = \{\s*\.\.\.previous,/s);
  assert.match(live, /dayChange:/);
  assert.match(live, /marketStatus:/);
  assert.match(live, /delayTime:/);
  assert.match(live, /localStorage\.setItem\(QUOTE_CACHE_KEY/);
});

test('DOM observer does not react to price text mutations', () => {
  assert.match(live, /mutation\.addedNodes/);
  assert.match(live, /node instanceof Element/);
  assert.match(live, /\[data-watch-card\], \[data-home-watch-open\]/);
  assert.doesNotMatch(live, /new MutationObserver\(\(\) => enhanceCachedRows\(\)\)/);
});

test('template loads rollback-safe additive live assets', () => {
  assert.match(html, /\/static\/css\/live_quotes_v56\.css\?v=/);
  assert.match(html, /\/static\/js\/live_quotes_v56\.js\?v=/);
  const bundle = html.indexOf('/static/js/chartview_release_bundle.js');
  const liveIndex = html.indexOf('/static/js/live_quotes_v56.js');
  const legacyPatch = html.indexOf('/static/js/ux_patch.js');
  assert.ok(bundle >= 0 && liveIndex > bundle && legacyPatch > liveIndex);
  assert.match(css, /prefers-reduced-motion/);
});

test('all watchlist cards keep a today-change slot even before a fresh quote arrives', () => {
  assert.match(live, /if \(card\) ensureLiveLine\(card\)/);
  assert.match(live, /오늘 —/);
  assert.match(live, /lastMode = ''/);
  assert.match(live, /setTimeout\(\(\) => tick\(false\), 0\)/);
  assert.match(live, /version: 'v64'/);
  assert.match(html, /\/static\/js\/live_quotes_v56\.js\?v=20260922v64a/);
});
