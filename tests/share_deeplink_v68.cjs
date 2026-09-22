const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const base = process.env.APP_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      locale: 'ko-KR',
      timezoneId: 'Asia/Seoul',
    });
    const page = await context.newPage();

    let response = await page.goto(`${base}/?tab=screener&view=ai-picks`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    assert.equal(response.status(), 200);

    await page.locator('#screener-tab.active').waitFor({ timeout: 20000 });
    await page.locator('#screener-tab [data-discovery-view="ai-picks"].active').waitFor({ timeout: 20000 });
    await page.waitForFunction(() => window.ChartViewShare?.version === 'v68', null, { timeout: 10000 });

    const pickUrl = new URL(await page.evaluate(() => window.ChartViewShare.buildUrl()));
    assert.equal(pickUrl.origin, 'https://chart-view-pkv8.onrender.com');
    assert.equal(pickUrl.searchParams.get('tab'), 'screener');
    assert.equal(pickUrl.searchParams.get('view'), 'ai-picks');
    assert.equal(pickUrl.searchParams.get('utm_source'), 'share');
    assert.equal(pickUrl.searchParams.get('utm_campaign'), 'chartview_v68');

    await page.evaluate(() => {
      const detail = window.ChartViewState.detail;
      detail.open = true;
      detail.symbol = 'NVDA';
      detail.name = '엔비디아';
    });
    const detailUrl = new URL(await page.evaluate(() => window.ChartViewShare.buildUrl()));
    assert.equal(detailUrl.searchParams.get('tab'), 'chart');
    assert.equal(detailUrl.searchParams.get('view'), 'detail');
    assert.equal(detailUrl.searchParams.get('symbol'), 'NVDA');
    assert.equal(detailUrl.searchParams.get('name'), '엔비디아');

    await context.close();
  } finally {
    await browser.close();
  }
  console.log('context share V68 deep-link OK');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
