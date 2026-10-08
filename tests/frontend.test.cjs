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
  const bootBundle = fs.readFileSync('static/js/chartview_boot_bundle.js', 'utf8');
  const sync = fs.readFileSync('static/js/profile_sync_v1.js', 'utf8');
  const service = fs.readFileSync('profile_sync_service.py', 'utf8');
  assert.match(html, /chartview_boot_bundle\.js\?v=/);
  assert.match(bootBundle, /\/\* --- static\/js\/profile_sync_v1\.js --- \*\//);
  assert.match(sync, /chartview-watchlist-v1/);
  assert.match(sync, /\/api\/profile-sync\//);
  assert.match(sync, /ID를 아는 사람은 해당 관심종목 목록을 불러오거나 변경할 수 있으므로/);
  assert.match(service, /hashlib\.sha256/);
  assert.match(service, /MAX_WATCHLIST = 20/);
  assert.match(service, /PROFILE_SYNC_DATABASE_URL/);
});

// A small DOM adapter exercises the real annotator without adding a CI browser
// dependency. Deferred responses stay unresolved until the test releases them.
function valuationHarness() {
  class Element {
    constructor(text = '') {
      this.nodeType = 1;
      this._text = text;
      this.childNodes = text ? [{ nodeType: 3, textContent: text }] : [];
      this.children = [];
      this.dataset = {};
      this.title = '';
      const classes = new Set();
      this.classList = {
        add: value => classes.add(value), remove: value => classes.delete(value),
        contains: value => classes.has(value),
        toggle: (value, enabled) => enabled ? classes.add(value) : classes.delete(value),
      };
    }
    get textContent() { return this.childNodes.length ? this.childNodes.map(n => n.textContent).join('') : this._text; }
    set textContent(value) { this._text = value; this.childNodes = [{ nodeType: 3, textContent: value }]; this.children = []; }
    replaceChildren(...nodes) { this._text = ''; this.childNodes = nodes; this.children = nodes.filter(n => n.nodeType === 1); }
    append(...nodes) { this.replaceChildren(...this.childNodes, ...nodes); }
    appendChild(node) { this.append(node); }
    set innerHTML(value) { this.textContent = value.replace(/<[^>]+>/g, ''); }
    removeAttribute(name) { if (name === 'title') this.title = ''; }
    querySelector(selector) {
      if (selector === ':scope > .metric-value-wrap > .metric-value-main') return this.querySelector('.metric-value-wrap')?.querySelector('.metric-value-main') || null;
      const cls = selector.replace(':scope > ', '').slice(1);
      for (const node of this.children) {
        if (node.className === cls || node.classList.contains(cls)) return node;
        const found = node.querySelector(selector);
        if (found) return found;
      }
      return null;
    }
  }
  const makeTable = ticker => {
    const cells = [new Element(ticker), new Element('old price'), new Element('old metric')];
    const row = { children: cells, querySelector: selector => selector === '.stock-ticker' ? { textContent: ticker } : null };
    const table = new Element();
    table.querySelectorAll = selector => selector === 'tbody tr' ? [row] : [];
    table.cells = cells;
    return table;
  };
  let table = makeTable('AAPL');
  const source = new Element();
  let mobile = true;
  let resolve, reject, requests = 0;
  const response = new Promise((yes, no) => { resolve = yes; reject = no; });
  const context = vm.createContext({
    window: { matchMedia: () => ({ matches: mobile }) },
    document: {
      readyState: 'loading', addEventListener() {},
      querySelector: selector => selector === '.per-source' ? source : selector === '#per-table-container .per-table' ? table : null,
      getElementById: id => id === 'per-table-container' ? { querySelectorAll: () => table.cells } : null,
      createTextNode: text => ({ nodeType: 3, textContent: text }),
      createElement: () => new Element(),
    },
    Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
    fetch: () => { requests += 1; return response; },
    perData: [{ ticker: 'AAPL', price: 250.15, forwardPE: 28.4, pbr: 45.1 }],
    currentMetric: 'overview',
    METRIC_CONFIG: { overview: { columns: [{ key: 'forwardPE', label: 'FWD PER', format: 'number' }] }, pbr: { columns: [{ key: 'pbr', label: 'PBR', format: 'number' }] } },
    formatValue: value => value == null ? '-' : Number(value).toFixed(1),
  });
  const code = fs.readFileSync('static/js/valuation_meta.js', 'utf8').replace(/\}\)\(\);\s*$/, 'window.test = { annotateTable }; })();');
  vm.runInContext(code, context);
  const basisCode = fs.readFileSync('static/js/release_ui_v40.js', 'utf8').replace(/\}\)\(\);\s*$/, 'window.basisTest = { addBasisControls }; })();');
  vm.runInContext(basisCode, context);
  return {
    context, source, annotate: () => context.window.test.annotateTable(),
    addBasisControls: () => context.window.basisTest.addBasisControls(),
    get table() { return table; }, get requests() { return requests; },
    replaceTable(ticker = 'AAPL') { table = makeTable(ticker); return table; },
    setMobile(value) { mobile = value; },
    reply(payload, ok = true) { resolve({ ok, json: async () => payload }); }, fail: reject,
  };
}

test('valuation mobile cards paint API labels and values before an unresolved optional cache', async () => {
  const h = valuationHarness();
  const annotation = h.annotate();
  const cells = h.table.cells;
  assert.ok(h.table.classList.contains('valuation-compact-table'));
  assert.deepEqual(cells.map(cell => cell.dataset.label), ['종목', '현재가', 'FWD PER']);
  assert.equal(cells[1].textContent, '$250.15');
  assert.equal(cells[2].textContent, '28.4');
  assert.equal(cells[1].title, '출처 확인 중');
  assert.doesNotMatch(h.source.textContent, /Yahoo 캐시|기준/);
  h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1, forwardPE: 2 } } });
  await annotation;
  assert.match(cells[1].title, /2026\.10\.07.*Yahoo 일일 캐시/);
  assert.match(cells[2].title, /예상 기간 미확인.*Yahoo 컨센서스 캐시/);
  assert.equal(cells[1].textContent, '$250.15', 'cache must never overwrite API values');
  assert.equal(cells[2].textContent, '28.4');
});

for (const failure of ['network', 'http']) {
  test(`valuation optional cache ${failure} failure preserves cards, absent values and exact API provenance`, async () => {
    const h = valuationHarness();
    h.context.perData = [{ ticker: '005930.KS', price: 266000, forwardPE: null, fieldMeta: { price: { source: 'Naver', asOf: '2026-10-07T15:30:00+09:00', period: 'latest trading value', method: 'provider' } } }];
    h.replaceTable('005930.KS');
    const annotation = h.annotate();
    assert.equal(h.table.cells[1].textContent, '₩266,000');
    assert.match(h.table.cells[1].title, /2026\.10\.07.*최근 거래값.*Naver/);
    assert.equal(h.table.cells[2].textContent, '-');
    assert.match(h.table.cells[2].title, /컨센서스 데이터 없음/);
    if (failure === 'network') h.fail(new Error('unavailable')); else h.reply(null, false);
    await annotation;
    assert.equal(h.table.cells[1].textContent, '₩266,000');
    assert.match(h.table.cells[1].title, /Naver/);
    assert.equal(h.table.cells[2].textContent, '-');
    assert.doesNotMatch(h.source.textContent, /Yahoo 캐시|기준/);
    assert.match(h.source.textContent, /캐시 출처 확인 불가/);
  });
}

test('valuation late cache ignores a replaced table and annotates only the current render', async () => {
  const h = valuationHarness();
  const oldTable = h.table;
  const old = h.annotate();
  h.replaceTable();
  const current = h.annotate();
  assert.equal(h.requests, 1, 'optional cache request remains singleflight');
  h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1 } } });
  await Promise.all([old, current]);
  assert.equal(oldTable.cells[1].title, '출처 확인 중');
  assert.match(h.table.cells[1].title, /Yahoo 일일 캐시/);
});

test('valuation late cache cannot apply an old metric to a reused table', async () => {
  const h = valuationHarness();
  const old = h.annotate();
  h.context.currentMetric = 'pbr';
  const current = h.annotate();
  assert.equal(h.table.cells[2].dataset.label, 'PBR');
  assert.equal(h.table.cells[2].textContent, '45.1');
  h.reply({ quotes: { AAPL: { priceToBook: 3 } } });
  await Promise.all([old, current]);
  assert.equal(h.table.cells[2].dataset.label, 'PBR');
  assert.equal(h.table.cells[2].textContent, '45.1');
  assert.doesNotMatch(h.table.cells[2].title, /컨센서스/);
});

test('valuation desktop labels and existing values remain available during cache delay', async () => {
  const h = valuationHarness();
  h.setMobile(false);
  h.table.cells[1].textContent = '$250.15';
  h.table.cells[2].textContent = '28.4';
  const annotation = h.annotate();
  assert.equal(h.table.classList.contains('valuation-compact-table'), false);
  assert.equal(h.table.cells[1].dataset.label, '현재가');
  assert.equal(h.table.cells[1].querySelector('.metric-value-main').textContent, '$250.15');
  assert.equal(h.table.cells[1].querySelector('.metric-provenance').textContent, '출처 확인 중');
  h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1 } } });
  await annotation;
  assert.equal(h.table.cells[1].querySelector('.metric-value-main').textContent, '$250.15');
  assert.match(h.table.cells[1].querySelector('.metric-provenance').textContent, /Yahoo 일일 캐시/);
});

test('valuation reentry uses completed optional metadata immediately without another request', async () => {
  const h = valuationHarness();
  const first = h.annotate();
  h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1 } } });
  await first;
  h.replaceTable();
  const next = h.annotate();
  assert.match(h.table.cells[1].title, /Yahoo 일일 캐시/);
  assert.equal(h.table.cells[1].textContent, '$250.15');
  assert.equal(h.requests, 1);
  await next;
});

test('valuation compact cells stay value-only when the actual release UI decorator runs before and after cache completion', async () => {
  const h = valuationHarness();
  const annotation = h.annotate();
  h.addBasisControls();
  assert.deepEqual(h.table.cells.slice(1).map(cell => cell.textContent), ['$250.15', '28.4']);
  assert.ok(h.table.cells.slice(1).every(cell => !cell.querySelector('.v40-cell-basis')));
  h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1, forwardPE: 2 } } });
  await annotation;
  h.addBasisControls();
  await h.annotate();
  h.addBasisControls();
  assert.deepEqual(h.table.cells.slice(1).map(cell => cell.textContent), ['$250.15', '28.4']);
  assert.ok(h.table.cells.slice(1).every(cell => cell.children.length === 0));
  assert.match(h.table.cells[1].title, /Yahoo 일일 캐시/);
  assert.equal(h.table.cells[1].dataset.provenance, h.table.cells[1].title);
});

test('valuation release UI keeps desktop basis controls and removes them when switching to compact cards', async () => {
  const h = valuationHarness();
  h.setMobile(false);
  h.table.cells[1].textContent = '$250.15';
  h.table.cells[2].textContent = '28.4';
  const first = h.annotate();
  h.addBasisControls();
  assert.ok(h.table.cells[1].querySelector('.v40-cell-basis'));
  h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1 } } });
  await first;
  h.addBasisControls();
  assert.ok(h.table.cells[1].querySelector('.v40-cell-basis'));
  assert.equal(h.table.cells[1].querySelector('.metric-value-main').textContent, '$250.15');
  h.setMobile(true);
  await h.annotate();
  h.addBasisControls();
  assert.equal(h.table.cells[1].querySelector('.v40-cell-basis'), null);
  assert.equal(h.table.cells[1].textContent, '$250.15');
  assert.match(h.table.cells[1].title, /Yahoo 일일 캐시/);
  h.setMobile(false);
  await h.annotate();
  h.addBasisControls();
  assert.ok(h.table.cells[1].querySelector('.v40-cell-basis'));
  assert.equal(h.table.cells[1].querySelector('.metric-value-main').textContent, '$250.15');
});

for (const change of ['table', 'metric', 'data', 'viewport']) {
  test(`valuation late cache ignores an obsolete ${change} without another annotation`, async () => {
    const h = valuationHarness();
    const original = h.table;
    const annotation = h.annotate();
    if (change === 'table') h.replaceTable();
    if (change === 'metric') h.context.currentMetric = 'pbr';
    if (change === 'data') h.context.perData = [{ ticker: 'AAPL', price: 999 }];
    if (change === 'viewport') h.setMobile(false);
    h.reply({ generatedAt: '2026-10-07T12:00:00+09:00', quotes: { AAPL: { regularMarketPrice: 1 } } });
    await annotation;
    assert.equal(original.cells[1].title, '출처 확인 중');
    assert.equal(original.cells[1].textContent, '$250.15');
    assert.doesNotMatch(h.source.textContent, /Yahoo 캐시|기준/);
  });
}
