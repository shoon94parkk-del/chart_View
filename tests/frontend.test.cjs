const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

test('promo keeps the directly loaded AI widget instead of replacing it', () => {
  const source = fs.readFileSync('static/js/promo_v1.js', 'utf8');
  assert.match(source, /script\[src\*="\/static\/js\/ai_daily_widget\.js"\]/);
  assert.doesNotMatch(source, /existing\.remove\(\)/);
  assert.doesNotMatch(source, /ai_daily_widget\.js\?v=20260914v5/);
});

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


test('2026-09-21 audit contracts keep date, detail and production states explicit', () => {
  const html = fs.readFileSync('templates/index.html', 'utf8');
  const chart = fs.readFileSync('static/js/chart.js', 'utf8');
  const detail = fs.readFileSync('static/js/single_detail_v40.js', 'utf8');
  const watch = fs.readFileSync('static/js/watchlist_v30.js', 'utf8');
  const quick = fs.readFileSync('static/js/watchlist_quick_add_v48.js', 'utf8');
  const workflow = fs.readFileSync('.github/workflows/app-check.yml', 'utf8');

  assert.match(html, /label for="start-date"/);
  assert.match(html, /id="custom-date-error"/);
  assert.match(html, /aria-label="비교종목 추가"/);
  assert.match(chart, /시작일은 종료일보다 빠르거나 같아야 합니다/);
  assert.match(chart, /미래 날짜는 조회할 수 없습니다/);
  assert.match(chart, /aria-busy/);
  assert.match(detail, /차트를 불러오는 중…/);
  assert.match(detail, /이 기간의 거래 데이터가 없습니다/);
  assert.match(detail, /detail-v42-zero-label/);
  assert.match(watch, /수익률 높은순/);
  assert.match(quick, /비교에 추가/);
  assert.match(workflow, /chart-view-pkv8\.onrender\.com/);
  assert.doesNotMatch(workflow, /chart-view-bsg6\.onrender\.com/);
  const pick = fs.readFileSync('static/js/ai_daily_widget.js', 'utf8');
  const p2 = fs.readFileSync('static/js/p2_revisit_v1.js', 'utf8');
  assert.match(pick, /최근 선정 PICK/);
  assert.match(pick, /추천 건별 평균 수익률/);
  assert.match(pick, /미평가 제외/);
  assert.match(detail, /관찰된 사실/);
  assert.match(detail, /비교할 기준/);
  assert.match(detail, /확인이 필요한 점/);
  assert.match(watch, /timeZone:\s*'Asia\/Seoul'/);
  assert.doesNotMatch(watch, /방금 갱신/);
  assert.match(p2, /window\.confirm\(preview\)/);
  assert.match(p2, /기존 관심종목은 그대로입니다/);
});
