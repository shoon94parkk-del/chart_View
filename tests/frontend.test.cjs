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
  const homeBrief = fs.readFileSync('static/js/home_brief_v8.js', 'utf8');
  const homeCss = fs.readFileSync('static/css/home_brief_v8.css', 'utf8');
  const releaseUi = fs.readFileSync('static/js/release_ui_v40.js', 'utf8');
  const continuityCss = fs.readFileSync('static/css/ui_continuity_v53.css', 'utf8');
  const screener = fs.readFileSync('static/js/screener.js', 'utf8');
  assert.match(releaseUi, /timeZone:\s*'Asia\/Seoul'/);
  assert.match(homeBrief, /data-home-stock-strip/);
  assert.match(homeBrief, /ArrowLeft/);
  assert.match(homeBrief, /ArrowRight/);
  assert.match(homeCss, /scroll-snap-type:x mandatory/);
  assert.match(homeCss, /home16-logo-fallback/);
  assert.match(continuityCss, /max-width:1120px/);
  assert.match(continuityCss, /home16-major-card\{grid-column:1\/-1;order:2/);
  assert.match(continuityCss, /grid-template-columns:repeat\(8,minmax\(0,1fr\)\)/);
  assert.match(continuityCss, /home16-strip-nav\{display:none\}/);
  assert.match(screener, /RSI 최소는 최대보다 클 수 없습니다/);
  assert.match(screener, /if \(errors\.length\) return false/);
  assert.match(p2, /<summary aria-label="관심종목 관리">관리<\/summary>/);
  const marketService = fs.readFileSync('market_service.py', 'utf8');
  assert.match(marketService, /"price": round\(close, 4\)/);
  assert.match(detail, /aria-live="polite"/);
  assert.match(detail, /point\.price/);
  assert.match(detail, /가격 \$\{priceText\}/);
  assert.match(detail, /midPoint/);
  assert.match(homeBrief, /marketSummaryHtml\(snapshot\?\.macro\) \+ majorStocksHtml/);
  assert.match(homeBrief, /<span>시장 상태<\/span><h3>시장 한줄 요약<\/h3>/);
  assert.match(watch, /summaryCard\.insertAdjacentElement\('afterend', section\)/);
  assert.match(homeBrief, /watchlistShortcut/);
});


test('passwordless watchlist sync keeps local-first behavior and explicit risk copy', () => {
  const html = fs.readFileSync('templates/index.html', 'utf8');
  const sync = fs.readFileSync('static/js/profile_sync_v1.js', 'utf8');
  const service = fs.readFileSync('profile_sync_service.py', 'utf8');
  assert.match(html, /profile_sync_v1\.js/);
  assert.match(sync, /chartview-watchlist-v1/);
  assert.match(sync, /\/api\/profile-sync\//);
  assert.match(sync, /ID를 아는 사람은 해당 관심종목 목록을 불러오거나 변경할 수 있으므로/);
  assert.match(service, /hashlib\.sha256/);
  assert.match(service, /MAX_WATCHLIST = 20/);
  assert.match(service, /PROFILE_SYNC_DATABASE_URL/);
});
