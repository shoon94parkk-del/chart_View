const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const BASE = process.env.APP_URL || 'http://127.0.0.1:8080';
const WATCHLIST = [
  { symbol: 'NVDA', name: '엔비디아' },
  { symbol: 'AAPL', name: '애플' },
  { symbol: '005930.KS', name: '삼성전자' },
];
const nvda1 = { symbol: 'NVDA', name: '엔비디아', title: 'NVIDIA announces earnings guidance update', source: 'Reuters', publishedAt: new Date(Date.now()-60000).toISOString(), publishedTs: Date.now()-60000, url: 'https://example.com/nvda1', score: 180 };
const nvda2 = { symbol: 'NVDA', name: '엔비디아', title: 'NVIDIA signs major supply contract', source: 'Example', publishedAt: new Date(Date.now()-120000).toISOString(), publishedTs: Date.now()-120000, url: 'https://example.com/nvda2', score: 150 };
const aapl1 = { symbol: 'AAPL', name: '애플', title: 'Apple board expands buyback plan', source: 'Example', publishedAt: new Date(Date.now()-180000).toISOString(), publishedTs: Date.now()-180000, url: 'https://example.com/aapl1', score: 140 };
const ss1 = { symbol: '005930.KS', name: '삼성전자', title: '삼성전자 신규 공급 계약 발표', source: '테스트뉴스', publishedAt: new Date(Date.now()-240000).toISOString(), publishedTs: Date.now()-240000, url: 'https://example.com/ss1', score: 160 };

const payload = {
  items: [nvda1, ss1, aapl1],
  errors: [],
  groups: [
    { symbol: 'NVDA', name: '엔비디아', status: 'success', items: [nvda1, nvda2] },
    { symbol: 'AAPL', name: '애플', status: 'success', items: [aapl1] },
    { symbol: '005930.KS', name: '삼성전자', status: 'success', items: [ss1] },
  ],
};

async function seed(context) {
  await context.addInitScript((rows) => {
    localStorage.setItem('chartview-watchlist-v1', JSON.stringify(rows));
  }, WATCHLIST);
}

async function mockData(page) {
  await page.route('**/api/personalized-news?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.route('**/api/compare?**', async route => {
    const values = [100, 103, 101, 106, 104, 108, 107, 110];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stocks: [{ data: values.map(close => ({ close })) }] }) });
  });
}

(async () => {
  const browser = await chromium.launch({ headless: true });

  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light' });
  await seed(context);
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  await mockData(page);

  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.app-bottom-btn[data-app-mode="watchlist"]');
  await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
  await page.waitForSelector('#watchlist-tab[data-my-hub-version="v41"]');

  const switchButtons = page.locator('[data-v41-switch] [data-v41-view]');
  assert.equal(await switchButtons.count(), 2, 'MY hub must expose stocks/news switch');
  assert.ok(await page.locator('#watchlist-v30-grid .watchlist-v33-card').count() >= 3, 'watchlist rows should remain available');

  await page.locator('[data-v41-view="news"]').click();
  await page.waitForSelector('.my-hub-v41-news:not([hidden])');
  await page.waitForSelector('.my-hub-v41-news-row');
  assert.equal(await page.locator('.my-hub-v41-news-row').count(), 4, 'full feed should flatten group articles');
  assert.equal(await page.locator('.my-hub-v41-news-row .news-v412-summary').count(), 4, 'every full-feed article should show a one-line summary');
  assert.ok(await page.getByText('실적', { exact: true }).count() >= 1, 'event category badge should be visible');
  assert.ok(await page.getByText('계약·수주', { exact: true }).count() >= 1, 'contract category badge should be visible');

  await page.locator('[data-v41-symbol="NVDA"]').click();
  assert.equal(await page.locator('.my-hub-v41-news-row').count(), 2, 'symbol filter should narrow feed');
  await page.locator('[data-v41-symbol="ALL"]').click();
  await page.locator('[data-v41-sort="relevance"]').click();
  assert.ok(await page.locator('[data-v41-sort="relevance"]').evaluate(el => el.classList.contains('active')), 'sort state should update');

  await page.locator('.app-bottom-btn[data-app-mode="home"]').click();
  await page.waitForSelector('#home-personal-news-v37 .news-v40-card .news-v412-summary');
  await page.waitForSelector('#home-personal-news-v37 .news-v412-market-ready');
  const chartBox = await page.locator('#home-personal-news-v37 .news-v412-market-ready svg').first().boundingBox();
  assert.ok(chartBox && chartBox.width > 240 && chartBox.height >= 70, `5D chart should use card width, got ${JSON.stringify(chartBox)}`);
  assert.ok(await page.locator('#home-personal-news-v37 .news-v412-market-metrics').first().getByText(/5D/).count(), '5D metrics should be visible');
  assert.ok(await page.locator('#home-personal-news-v37 .news-v412-chart-axis').first().getByText('현재', { exact: true }).count(), 'chart should label current endpoint');

  await page.waitForSelector('#home-personal-news-v37 .v41-news-all');
  await page.locator('#home-personal-news-v37 .v41-news-all').click();
  await page.waitForSelector('.my-hub-v41-news:not([hidden])');
  assert.ok(await page.locator('[data-v41-view="news"]').evaluate(el => el.classList.contains('active')), 'home all-news should open MY news view');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(overflow, false, '390px hub should not horizontally overflow');
  assert.deepEqual(errors, [], `page errors: ${errors.join('\n')}`);
  await context.close();

  const raceContext = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light' });
  await seed(raceContext);
  const racePage = await raceContext.newPage();
  racePage.setDefaultTimeout(12000);
  await racePage.route('**/static/js/home_brief_v8.js*', async route => {
    await new Promise(resolve => setTimeout(resolve, 1200));
    await route.continue();
  });
  await racePage.goto(BASE, { waitUntil: 'domcontentloaded' });
  await racePage.waitForSelector('.app-bottom-btn[data-app-mode="watchlist"]');
  await racePage.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
  await racePage.waitForSelector('#watchlist-tab');
  await racePage.waitForTimeout(1600);
  assert.ok(await racePage.locator('.app-bottom-btn[data-app-mode="watchlist"]').evaluate(el => el.classList.contains('active')), 'late Home asset must not override user navigation');
  assert.ok(await racePage.locator('#watchlist-tab').isVisible(), 'watchlist view must remain visible after late Home asset load');
  await raceContext.close();

  console.log('V41_MY_HUB_PASS');
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });