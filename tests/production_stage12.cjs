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
  await context.addInitScript(() => {
    localStorage.setItem('chartview-watchlist-v1', JSON.stringify([
      { symbol: 'DELL', name: 'DELL' },
      { symbol: 'NVDA', name: '엔비디아' },
      { symbol: 'AAPL', name: '애플' },
    ]));
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  try {
    const response = await page.goto(`${BASE}/?production_stage12=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    assert.equal(response.status(), 200);

    // Consensus previously regressed to 503 whenever Yahoo's crumb endpoint rate-limited.
    // Keep a real production check here so stale-but-valid scheduled snapshots must remain usable.
    const consensusResponse = await context.request.get(`${BASE}/api/consensus?ticker=AAPL&production_stage12=${Date.now()}`, { timeout: 30000 });
    assert.equal(consensusResponse.status(), 200, `production consensus status ${consensusResponse.status()}`);
    const consensus = await consensusResponse.json();
    assert.ok(consensus && consensus.periods && Object.keys(consensus.periods).length > 0, 'production consensus periods empty');
    assert.ok(['daily', 'stale', 'live'].includes(consensus.cacheMode), `unexpected consensus cacheMode ${consensus.cacheMode}`);

    await page.waitForFunction(() => window.ChartViewState?.version === 'v40' && typeof window.__openStockDetail === 'function', null, { timeout: 30000 });
    await page.waitForSelector('#home-tab .home-v8.home16-market-home #home-v8-body', { state: 'visible', timeout: 30000 });

    await page.locator('#home-watchlist-v30').waitFor({ timeout: 30000 });
    const homeOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(homeOverflow <= 2, `production home overflow ${homeOverflow}`);
    await page.screenshot({ path: path.join(OUT, 'home-390.png'), fullPage: true });

    // Direct live-production regression for the user's MY NEWS expansion path.
    // This intentionally uses the deployed assets and real personalized-news feed rather than the mocked hub test.
    await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
    await page.waitForSelector('#watchlist-tab', { state: 'visible', timeout: 30000 });
    await page.waitForSelector('[data-v41-view="news"]', { state: 'visible', timeout: 30000 });
    await page.locator('[data-v41-view="news"]').click();
    await page.waitForSelector('.my-hub-v41-news-row .news-v412-summary:not(.is-loading)', { state: 'visible', timeout: 60000 });

    const summary = page.locator('.my-hub-v41-news-row .news-v412-summary:not(.is-loading)').first();
    const summaryHandle = await summary.elementHandle();
    assert.ok(summaryHandle, 'production MY news summary handle missing');
    const realSummaryText = (await summary.locator('.news-v417-summary-text').innerText()).trim();
    assert.ok(realSummaryText.length > 0, 'production MY news summary text empty');

    // If the current live article happens to fit in two lines, make the already-rendered production
    // summary longer so we still validate the deployed click/overflow behavior on the real DOM.
    const naturallyClipped = await summary.locator('.news-v417-summary-text').evaluate((el) => el.scrollHeight > el.clientHeight + 2);
    if (!naturallyClipped) {
      await summary.locator('.news-v417-summary-text').evaluate((el) => {
        el.textContent = `${el.textContent} · 전체보기 검증용 긴 문장입니다. `.repeat(8);
      });
    }
    const summaryBefore = await summary.locator('.news-v417-summary-text').evaluate((el) => ({
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      clamp: getComputedStyle(el).webkitLineClamp,
    }));
    assert.ok(summaryBefore.scrollHeight > summaryBefore.clientHeight + 2, `production summary not clipped before expansion ${JSON.stringify(summaryBefore)}`);

    await summaryHandle.click();
    await page.waitForFunction((box) => box?.getAttribute('aria-expanded') === 'true', summaryHandle);
    const summaryAfter = await summaryHandle.evaluate((box) => {
      const text = box.querySelector('.news-v417-summary-text');
      const row = box.closest('.my-hub-v41-news-row');
      const style = getComputedStyle(text);
      const rowRect = row?.getBoundingClientRect();
      const textRect = text.getBoundingClientRect();
      return {
        ariaExpanded: box.getAttribute('aria-expanded'),
        buttonText: box.querySelector('.news-v417-summary-head i')?.textContent,
        clientHeight: text.clientHeight,
        scrollHeight: text.scrollHeight,
        clamp: style.webkitLineClamp,
        overflow: style.overflow,
        rowClientHeight: row?.clientHeight || 0,
        rowScrollHeight: row?.scrollHeight || 0,
        rowBottom: rowRect?.bottom || 0,
        textBottom: textRect.bottom,
        connected: box.isConnected,
      };
    });
    assert.equal(summaryAfter.ariaExpanded, 'true');
    assert.equal(summaryAfter.connected, true, 'expanded production summary was replaced during interaction');
    assert.equal(summaryAfter.buttonText, '접기');
    assert.ok(summaryAfter.clientHeight >= summaryAfter.scrollHeight - 1, `production summary still clipped ${JSON.stringify(summaryAfter)}`);
    // The lead card has an intentionally clipped decorative pseudo-element, so
    // row scrollHeight is larger than clientHeight even when the text is visible.
    assert.ok(summaryAfter.textBottom <= summaryAfter.rowBottom + 1, `production MY news row still clips expanded summary ${JSON.stringify(summaryAfter)}`);
    await page.screenshot({ path: path.join(OUT, 'my-news-expanded-390.png'), fullPage: true });

    await page.evaluate(() => window.__openAppTab('home'));
    await page.waitForSelector('#home-tab', { state: 'visible', timeout: 10000 });

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
    console.log('PRODUCTION_STAGE12_PASS', JSON.stringify({ detailChartTop, compareTop, priceText, compareText, consensusCacheMode: consensus.cacheMode, realSummaryTextLength: realSummaryText.length, summaryBefore, summaryAfter }));
  } finally {
    await context.close();
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
