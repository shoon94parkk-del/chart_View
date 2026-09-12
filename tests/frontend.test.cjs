const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function load(file, exports = '', storage = {}) {
  const context = vm.createContext({
    window: {}, document: { readyState: 'loading', addEventListener() {} },
    localStorage: { getItem: key => storage[key] ?? null },
    LightweightCharts: { CrosshairMode: { Normal: 0 } }, console,
  });
  let code = fs.readFileSync(file, 'utf8');
  if (exports) code = code.replace(/\}\)\(\);\s*$/, `window.test = { ${exports} }; })();`);
  vm.runInContext(code, context);
  return context;
}

test('Korean local dates do not move YTD into last year', () => {
  process.env.TZ = 'Asia/Seoul';
  const c = load('static/js/chart.js');
  assert.equal(vm.runInContext('localDate(new Date(2026, 0, 1))', c), '2026-01-01');
  assert.equal(vm.runInContext('localDate(new Date(2026, 8, 12, 0, 10))', c), '2026-09-12');
});

test('missing consensus does not become zero or -100% revision', () => {
  const { num, changePct } = load('static/js/consensus_v2.js', 'num, changePct').window.test;
  for (const x of [null, undefined, '', NaN, Infinity]) assert.equal(num(x), null);
  assert.equal(num(0), 0);
  assert.equal(changePct(null, 10), null);
  assert.equal(changePct(0, 10), -100);
});

test('malformed saved watchlist does not crash and missing quotes stay missing', () => {
  const t = load('static/js/watchlist_v30.js', 'formatPrice, returnText, watchlist', {
    'chartview-watchlist-v1': '{}', 'chartview-recents-v1': 'null',
  }).window.test;
  assert.equal(t.watchlist.length, 3);
  assert.equal(t.formatPrice('005930.KS', null), '-');
  assert.equal(t.returnText(null), '-');
  assert.equal(t.returnText(0), '0.00%');
});

test('revision and price-return difference is shown in percentage points', () => {
  const { pctPoint } = load('static/js/decision_ux_v7.js', 'pctPoint').window.test;
  assert.equal(pctPoint(12.1), '+12.1%p');
  assert.equal(pctPoint(-2), '-2.0%p');
  assert.equal(pctPoint(null), '-');
});
