const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const BASE = process.env.APP_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light' });
  await context.addInitScript(() => {
    localStorage.setItem('chartview-watchlist-v1', JSON.stringify([
      { symbol: '005930.KS', name: '삼성전자' },
      { symbol: 'NVDA', name: '엔비디아' },
      { symbol: 'AAPL', name: '애플' },
      { symbol: 'MSFT', name: '마이크로소프트' },
    ]));
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);

  await page.route('**/api/market-now**', async route => {
    const symbols = ['^KS11','^KQ11','^GSPC','^IXIC','^TNX','^VIX','CL=F','KRW=X'];
    const values = [2740,880,6050,19200,4.18,16.5,67.2,1388];
    const results = symbols.map((ticker, i) => ({ ticker, price: values[i], change: i % 2 ? -0.7 : 0.9, asOf: '2026-09-12' }));
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ timestamp: '2026-09-13 14:30:00', results, errors: [] }) });
  });

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#home-market-v9 [data-v40-market-more]');
  await page.waitForSelector('#home-watchlist-v30[data-visual-version="v41.4"]');

  const toggle = page.locator('#home-market-v9 [data-v40-market-more]');
  assert.match(await toggle.textContent(), /시장 지표 4개 더 보기/);
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');

  const visibleMarketCount = async () => page.locator('#home-market-v9-grid > .home-market-v9-item:visible').count();
  assert.equal(await visibleMarketCount(), 4, 'collapsed market should show four primary indicators');
  await toggle.click();
  await page.waitForFunction(() => document.getElementById('home-market-v9')?.classList.contains('v40-market-expanded'));
  assert.equal(await visibleMarketCount(), 8, 'expanded market should visibly show all eight indicators');
  assert.match(await toggle.textContent(), /접기/);
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
  const gridDisplay = await page.locator('#home-market-v9-grid').evaluate(el => getComputedStyle(el).display);
  assert.equal(gridDisplay, 'grid', 'mobile expanded market must be a visible grid, not a hidden horizontal rail');

  const watch = page.locator('#home-watchlist-v30');
  const watchBg = await watch.evaluate(el => getComputedStyle(el).backgroundImage);
  assert.notEqual(watchBg, 'none', 'MY stocks section should have a deliberate visual surface');
  const firstCard = page.locator('#home-watchlist-v30 [data-home-watch-open]').first();
  const cardShadow = await firstCard.evaluate(el => getComputedStyle(el).boxShadow);
  assert.notEqual(cardShadow, 'none', 'MY stock rows should be visually separated from the section surface');
  const allButton = page.locator('#home-watchlist-v30 [data-home-watch-all]');
  assert.equal(await allButton.getAttribute('aria-label'), '관심종목 전체 보기');
  assert.ok((await firstCard.getAttribute('aria-label'))?.includes('상세 보기'));

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(overflow, false, 'V41.4 Home should not create horizontal overflow at 390px');

  await browser.close();
  console.log('V41_4_HOME_PASS');
})().catch(err => { console.error(err); process.exit(1); });
