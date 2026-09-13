const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const BASE = process.env.APP_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light' });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);

  await page.addInitScript(() => {
    localStorage.setItem('chartview-watchlist-v1', JSON.stringify([
      { symbol: 'NVDA', name: '엔비디아' },
      { symbol: 'AAPL', name: '애플' },
      { symbol: '005930.KS', name: '삼성전자' },
    ]));
  });

  const payload = {
    items: [],
    errors: [],
    groups: [
      { symbol: 'NVDA', name: '엔비디아', status: 'success', items: [
        { symbol: 'NVDA', name: '엔비디아', title: 'NVIDIA announces earnings guidance update', source: 'Reuters', publishedAt: new Date(Date.now()-60000).toISOString(), publishedTs: Date.now()-60000, url: 'https://example.com/nvda1', score: 180 },
        { symbol: 'NVDA', name: '엔비디아', title: 'NVIDIA signs major supply contract', source: 'Example', publishedAt: new Date(Date.now()-120000).toISOString(), publishedTs: Date.now()-120000, url: 'https://example.com/nvda2', score: 150 },
      ]},
      { symbol: 'AAPL', name: '애플', status: 'success', items: [
        { symbol: 'AAPL', name: '애플', title: 'Apple board expands buyback plan', source: 'Example', publishedAt: new Date(Date.now()-180000).toISOString(), publishedTs: Date.now()-180000, url: 'https://example.com/aapl1', score: 140 },
      ]},
      { symbol: '005930.KS', name: '삼성전자', status: 'success', items: [
        { symbol: '005930.KS', name: '삼성전자', title: '삼성전자 신규 공급 계약 발표', source: '테스트뉴스', publishedAt: new Date(Date.now()-240000).toISOString(), publishedTs: Date.now()-240000, url: 'https://example.com/ss1', score: 160 },
      ]},
    ],
  };

  await page.route('**/api/personalized-news?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.route('**/api/compare?**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stocks: [] }) });
  });

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
  assert.ok(await page.getByText('실적', { exact: true }).count() >= 1, 'event category badge should be visible');
  assert.ok(await page.getByText('계약·수주', { exact: true }).count() >= 1, 'contract category badge should be visible');

  await page.locator('[data-v41-symbol="NVDA"]').click();
  assert.equal(await page.locator('.my-hub-v41-news-row').count(), 2, 'symbol filter should narrow feed');
  await page.locator('[data-v41-symbol="ALL"]').click();
  await page.locator('[data-v41-sort="relevance"]').click();
  assert.ok(await page.locator('[data-v41-sort="relevance"]').evaluate(el => el.classList.contains('active')), 'sort state should update');

  await page.locator('.app-bottom-btn[data-app-mode="home"]').click();
  await page.waitForSelector('#home-personal-news-v37 .v41-news-all');
  await page.locator('#home-personal-news-v37 .v41-news-all').click();
  await page.waitForSelector('.my-hub-v41-news:not([hidden])');
  assert.ok(await page.locator('[data-v41-view="news"]').evaluate(el => el.classList.contains('active')), 'home all-news should open MY news view');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(overflow, false, '390px hub should not horizontally overflow');
  assert.deepEqual(errors, [], `page errors: ${errors.join('\n')}`);
  console.log('V41_MY_HUB_PASS');
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });