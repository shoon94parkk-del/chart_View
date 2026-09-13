const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8080';
const OUT = path.join('test-results', 'stage12');
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function withTimeout(label, promise, ms = 10000) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms); }),
  ]).finally(() => clearTimeout(timer));
}

function comparePayload(symbol, delay = 0, overrides = {}) {
  const prices = [100, 101, 99, 103, 104];
  return {
    delay,
    body: {
      stocks: [{
        ticker: symbol,
        name: overrides.name || symbol,
        price: overrides.price ?? 1234.56,
        return: overrides.return ?? -7.25,
        data: prices.map((p, i) => ({ time: 1726000000 + i * 86400, value: Number((((p / prices[0]) - 1) * 100).toFixed(2)) })),
        actualStart: '2026-08-12', actualEnd: '2026-09-11', startDate: '2026-08-12', endDate: '2026-09-11',
        observations: 5, priceBasis: 'adjusted_close',
      }], errors: [],
    },
  };
}

async function installApiMocks(page, opts = {}) {
  const detailDelays = opts.detailDelays || {};
  await page.route('**/api/compare?**', async (route) => {
    const url = new URL(route.request().url());
    const tickers = decodeURIComponent(url.searchParams.get('tickers') || '').split(',').filter(Boolean);
    const period = url.searchParams.get('period') || '1mo';
    if (!tickers.length) return route.continue();
    if (tickers.length === 1) {
      const symbol = tickers[0];
      const mock = comparePayload(symbol, detailDelays[symbol] || (period === '5d' ? (opts.marketDelay || 0) : 0), {
        name: symbol === 'NVDA' ? '엔비디아' : symbol === 'AAPL' ? '애플' : symbol,
        price: symbol === '005930.KS' ? 1812000 : symbol === 'NVDA' ? 189.45 : 1234.56,
        return: symbol === 'TSLA' ? -123.45 : -7.25,
      });
      if (mock.delay) await sleep(mock.delay);
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mock.body) });
    }
    const stocks = tickers.map((symbol, idx) => comparePayload(symbol, 0, { price: symbol === '005930.KS' ? 1812000 : 100 + idx, return: idx - 2 }).body.stocks[0]);
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stocks, errors: [] }) });
  });

  await page.route('**/api/valuation?**', async (route) => {
    const url = new URL(route.request().url());
    const symbol = decodeURIComponent(url.searchParams.get('tickers') || 'NVDA').split(',')[0];
    if (detailDelays[symbol]) await sleep(detailDelays[symbol]);
    const row = opts.missingValues ? {
      ticker: symbol, price: 0, forwardPE: null, trailingPE: '', roe: 0, dividendYield: 0,
      pbr: Number.NaN, psr: Infinity, evEbitda: undefined,
    } : {
      ticker: symbol, price: 1234.56, forwardPE: 22.5, trailingPE: 28.1, roe: 18.4,
      dividendYield: 0.7, pbr: 5.2, psr: 8.1, evEbitda: 19.4,
      fieldMeta: {
        forwardPE: { asOf: '2026-09-11', period: 'provider forward period (not independently verified)', source: 'Yahoo' },
        roe: { asOf: '2026-06-30', period: 'TTM/latest reported', source: 'Yahoo Fundamentals' },
      },
    };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stocks: [row], errors: [] }) });
  });

  await page.route('**/api/consensus?**', async (route) => {
    const url = new URL(route.request().url());
    const symbol = url.searchParams.get('ticker') || 'NVDA';
    if (detailDelays[symbol]) await sleep(detailDelays[symbol]);
    const period = opts.missingValues
      ? { epsTrend: { current: null, '30daysAgo': 0 }, earnings: { avg: null } }
      : { epsTrend: { current: 5.5, '30daysAgo': 5.0 }, earnings: { avg: 5.5 } };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ periods: { '0y': period } }) });
  });
}

async function newPage(browser, { width = 390, height = 844, storage = {}, colorScheme = 'light', mocks = {} } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, colorScheme });
  await context.addInitScript((values) => {
    Object.entries(values).forEach(([key, value]) => localStorage.setItem(key, JSON.stringify(value)));
  }, storage);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await installApiMocks(page, mocks);
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForFunction(() => window.ChartViewState && window.ChartViewData && window.__openStockDetail && window.__reloadPersonalizedNewsV40, null, { timeout: 12000 });
  return { context, page, pageErrors };
}

async function scenarioDetailNoHangAndCompareState(browser) {
  const { context, page, pageErrors } = await newPage(browser, { width: 390, height: 844 });
  try {
    await withTimeout('NVDA detail open', page.evaluate(() => window.__openStockDetail('NVDA', '엔비디아', { instant: true })), 6000);
    await page.waitForSelector('#stock-detail-v40:not([hidden]) .detail-v40-id', { timeout: 3000 });
    assert.match(await page.locator('.detail-v40-id').innerText(), /엔비디아.*NVDA/s);
    assert.equal((await page.locator('[data-detail-compare]').innerText()).trim(), '비교 중');
    const top = await page.locator('.detail-v40-chart').evaluate((el) => el.getBoundingClientRect().top);
    assert.ok(top <= 420, `mobile single detail chart top ${top} > 420`);
    assert.equal(pageErrors.filter((x) => /RangeError|recursion|Maximum call stack/i.test(x)).length, 0, pageErrors.join('\n'));
    await page.screenshot({ path: path.join(OUT, 'detail-mobile.png'), fullPage: true });
  } finally { await context.close(); }
}

async function scenarioEmptyAndFullCompare(browser) {
  {
    const { context, page } = await newPage(browser, { storage: { 'chartview-selected-tickers-v1': [] } });
    try {
      assert.deepEqual(await page.evaluate(() => window.ChartViewState.getCompare().items), []);
      await page.evaluate(() => window.__openStockDetail('NVDA', '엔비디아', { instant: true }));
      await page.waitForSelector('[data-detail-compare]');
      assert.equal((await page.locator('[data-detail-compare]').innerText()).trim(), '비교에 추가');
    } finally { await context.close(); }
  }
  {
    const six = ['AAPL','NVDA','MSFT','META','TSLA','GOOGL'];
    const { context, page } = await newPage(browser, { storage: { 'chartview-selected-tickers-v1': six } });
    try {
      await page.evaluate(() => window.__openStockDetail('AMD', 'AMD', { instant: true }));
      await page.waitForSelector('[data-detail-compare]');
      assert.equal((await page.locator('[data-detail-compare]').innerText()).trim(), '비교목록 관리');
      assert.deepEqual(await page.evaluate(() => window.ChartViewState.getCompare().items), six);
    } finally { await context.close(); }
  }
}

async function scenarioMissingNumbers(browser) {
  const { context, page } = await newPage(browser, { mocks: { missingValues: true } });
  try {
    await page.evaluate(() => window.__openStockDetail('NVDA', '엔비디아', { instant: true }));
    await page.waitForSelector('[data-detail-tab="value"]');
    await page.locator('[data-detail-tab="value"]').click();
    const text = await page.locator('[data-detail-panel="value"]').innerText();
    assert.match(text, /FWD PER\s+—/);
    assert.match(text, /PER\s+—/);
    assert.match(text, /ROE\s+\+?0(?:\.0+)?%/);
    assert.match(text, /배당수익률\s+\+?0(?:\.0+)?%/);
    assert.doesNotMatch(text, /NaN|Infinity/);
  } finally { await context.close(); }
}

async function scenarioRaceAndClose(browser) {
  const { context, page } = await newPage(browser, { mocks: { detailDelays: { AAPL: 700, NVDA: 30 } } });
  try {
    page.evaluate(() => window.__openStockDetail('AAPL', '애플', { instant: true }));
    await sleep(30);
    await page.evaluate(() => window.__openStockDetail('NVDA', '엔비디아', { instant: true }));
    await page.waitForFunction(() => document.querySelector('.detail-v40-id')?.textContent?.includes('NVDA'), null, { timeout: 3000 });
    await sleep(900);
    assert.match(await page.locator('.detail-v40-id').innerText(), /NVDA/);
    assert.doesNotMatch(await page.locator('.detail-v40-id').innerText(), /AAPL/);

    page.evaluate(() => window.__openStockDetail('AAPL', '애플', { instant: true }));
    await sleep(30);
    await page.evaluate(() => window.__closeStockDetail({ force: true, restore: false }));
    await sleep(900);
    assert.equal(await page.locator('#stock-detail-v40').evaluate((el) => el.hidden), true);
    assert.equal(await page.evaluate(() => document.body.classList.contains('app-detail-v40-open')), false);
  } finally { await context.close(); }
}

async function scenarioNewsTwentyAndNonBlocking(browser) {
  const watchlist = Array.from({ length: 20 }, (_, i) => ({ symbol: `T${String(i + 1).padStart(2, '0')}`, name: `테스트${i + 1}` }));
  const { context, page } = await newPage(browser, { storage: { 'chartview-watchlist-v1': watchlist }, mocks: { marketDelay: 1600 } });
  let requestedCount = 0;
  try {
    await page.route('**/api/personalized-news?**', async (route) => {
      const url = new URL(route.request().url());
      requestedCount = (url.searchParams.get('tickers') || '').split(',').filter(Boolean).length;
      const groups = watchlist.map((row, i) => ({ symbol: row.symbol, name: row.name, items: i < 3 ? [{}] : [], status: i === 19 ? 'error' : i < 3 ? 'success' : 'no_news' }));
      const items = [0,1,2].map((i) => ({ symbol: watchlist[i].symbol, name: watchlist[i].name, title: `핵심 기사 ${i + 1}`, source: '테스트뉴스', publishedAt: new Date().toISOString(), url: `https://example.com/${i}`, score: 150 - i * 10 }));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items, groups, errors: [{ symbol: watchlist[19].symbol, code: 'provider_error:Timeout' }] }) });
    });
    const started = Date.now();
    await page.evaluate(() => window.__reloadPersonalizedNewsV40(true));
    await page.waitForSelector('.news-v40-card h4', { timeout: 2500 });
    const elapsed = Date.now() - started;
    assert.equal(requestedCount, 20);
    assert.ok(elapsed < 1500, `article rendering waited for market context: ${elapsed}ms`);
    assert.match(await page.locator('.news-v40-status').innerText(), /부분 실패/);
    assert.match(await page.locator('.news-v40-groups').innerText(), /조회 실패/);
    assert.match(await page.locator('.news-v40-card').first().innerText(), /이벤트 참고 설명/);
  } finally { await context.close(); }
}

async function scenarioResponsiveHomeAndCompare(browser) {
  for (const width of [360, 390, 430]) {
    const storage = { 'chartview-watchlist-v1': [{ symbol: '005930.KS', name: '아주 긴 테스트 종목명 삼성전자 우선주' }] };
    const { context, page } = await newPage(browser, { width, height: 844, storage, colorScheme: width === 390 ? 'dark' : 'light' });
    try {
      await page.waitForSelector('[data-home-watch-open="005930.KS"]', { timeout: 5000 });
      await page.waitForFunction(() => document.querySelector('[data-home-watch-price]')?.textContent?.includes('1,812,000'), null, { timeout: 5000 });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      assert.ok(overflow <= 2, `${width}px document horizontal overflow ${overflow}`);
      const price = await page.locator('[data-home-watch-price]').first().innerText();
      assert.equal(price, '₩1,812,000');
      const clipped = await page.locator('[data-home-watch-price]').first().evaluate((el) => el.scrollWidth > el.clientWidth + 2);
      assert.equal(clipped, false, `${width}px price clipped`);
      if (width === 390) await page.screenshot({ path: path.join(OUT, 'home-mobile-dark.png'), fullPage: true });
    } finally { await context.close(); }
  }

  for (const spec of [{ width: 390, height: 844, maxTop: 420 }, { width: 1366, height: 900, maxTop: 360 }]) {
    const { context, page } = await newPage(browser, spec);
    try {
      await page.evaluate(() => window.__openAppTab('chart'));
      await page.waitForSelector('#chart-container');
      await sleep(300);
      const top = await page.locator('#chart-container').evaluate((el) => el.getBoundingClientRect().top);
      assert.ok(top <= spec.maxTop, `${spec.width}px comparison chart top ${top} > ${spec.maxTop}`);
      if (spec.width === 1366) await page.screenshot({ path: path.join(OUT, 'comparison-desktop.png'), fullPage: true });
    } finally { await context.close(); }
  }
}

async function scenarioKeyboardAndStorageFailure(browser) {
  const { context, page } = await newPage(browser, { colorScheme: 'dark' });
  try {
    await page.evaluate(() => {
      const base = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === 'chartview-watchlist-v1') throw new Error('injected quota failure');
        return base.call(this, key, value);
      };
    });
    await page.evaluate(() => window.__openStockDetail('MSFT', '마이크로소프트', { instant: true }));
    await page.waitForSelector('[data-detail-watch]');
    await page.locator('[data-detail-watch]').focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('#v40-storage-warning:not([hidden])', { timeout: 2500 });
    assert.match(await page.locator('#v40-storage-warning').innerText(), /저장하지 못했습니다/);
    const minTouch = await page.locator('[data-detail-watch]').evaluate((el) => { const r = el.getBoundingClientRect(); return [r.width, r.height]; });
    assert.ok(minTouch[1] >= 44, `detail watch touch height ${minTouch[1]}`);
  } finally { await context.close(); }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const scenarios = [
    ['detail-no-hang', scenarioDetailNoHangAndCompareState],
    ['empty-full-compare', scenarioEmptyAndFullCompare],
    ['missing-numbers', scenarioMissingNumbers],
    ['race-close', scenarioRaceAndClose],
    ['news-20-nonblocking', scenarioNewsTwentyAndNonBlocking],
    ['responsive-home-compare', scenarioResponsiveHomeAndCompare],
    ['keyboard-storage-failure', scenarioKeyboardAndStorageFailure],
  ];
  try {
    for (const [name, fn] of scenarios) {
      const start = Date.now();
      await withTimeout(name, fn(browser), 30000);
      console.log(`PASS ${name} ${Date.now() - start}ms`);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
