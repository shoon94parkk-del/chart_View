const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const BASE = process.env.APP_URL || 'https://chart-view-bsg6.onrender.com';
const OUT = path.join('test-results', 'production-stage12');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  try {
    const response = await page.goto(`${BASE}/?production_stage12=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    assert.equal(response.status(), 200);
    await page.waitForFunction(() => window.ChartViewState?.version === 'v40' && typeof window.__openStockDetail === 'function', null, { timeout: 30000 });
    await page.waitForFunction(() => document.querySelector('#home-tab .home-v8')?.dataset?.uiVersion === 'v40-stage12', null, { timeout: 30000 });

    await page.locator('#home-watchlist-v30').waitFor({ timeout: 30000 });
    const homeOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(homeOverflow <= 2, `production home overflow ${homeOverflow}`);
    await page.screenshot({ path: path.join(OUT, 'home-390.png'), fullPage: true });

    await page.evaluate(() => window.__openStockDetail('NVDA', '엔비디아', { instant: true }));
    await page.waitForSelector('#stock-detail-v40:not([hidden]) .detail-v40-id', { timeout: 30000 });
    const detailId = await page.locator('.detail-v40-id').innerText();
    assert.match(detailId, /엔비디아.*NVDA/s);
    const compareText = (await page.locator('[data-detail-compare]').innerText()).trim();
    assert.equal(compareText, '비교 중');
    const detailChartTop = await page.locator('.detail-v40-chart').evaluate((el) => el.getBoundingClientRect().top);
    assert.ok(detailChartTop <= 420, `production detail chart top ${detailChartTop}`);
    const priceText = (await page.locator('.detail-v40-price strong').innerText()).trim();
    assert.ok(priceText.length > 0, 'production detail price text empty');
    await page.screenshot({ path: path.join(OUT, 'detail-nvda-390.png'), fullPage: true });

    await page.evaluate(() => window.__closeStockDetail({ force: true, restore: false }));
    await page.waitForFunction(() => document.getElementById('stock-detail-v40')?.hidden === true, null, { timeout: 5000 });
    assert.equal(await page.evaluate(() => document.body.classList.contains('app-detail-v40-open')), false);

    await page.evaluate(() => window.__openAppTab('chart'));
    await page.waitForSelector('#chart-tab.active #chart-container', { timeout: 30000 });
    await page.waitForSelector('#legend .legend-item', { timeout: 30000 });
    const compareTop = await page.locator('#chart-container').evaluate((el) => el.getBoundingClientRect().top);
    assert.ok(compareTop <= 420, `production comparison chart top ${compareTop}`);
    await page.screenshot({ path: path.join(OUT, 'compare-390.png'), fullPage: true });

    assert.equal(pageErrors.length, 0, pageErrors.join('\n'));
    console.log('PRODUCTION_STAGE12_PASS', JSON.stringify({ detailChartTop, compareTop, priceText, compareText }));
  } finally {
    await context.close();
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
