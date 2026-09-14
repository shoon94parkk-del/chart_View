const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const BASE = process.env.APP_URL || 'https://chart-view-bsg6.onrender.com';

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
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));

  try {
    const response = await page.goto(`${BASE}/?live_news_expand=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    assert.equal(response.status(), 200);
    await page.waitForFunction(() => typeof window.__openAppTab === 'function' && window.ChartViewState?.version === 'v40', null, { timeout: 30000 });

    await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
    await page.waitForSelector('#watchlist-tab', { state: 'visible' });
    await page.waitForSelector('[data-v41-view="news"]', { state: 'visible' });
    await page.locator('[data-v41-view="news"]').click();
    await page.waitForSelector('.my-hub-v41-news-row .news-v412-summary:not(.is-loading)', { state: 'visible', timeout: 60000 });

    let index = -1;
    for (let attempt = 0; attempt < 30 && index < 0; attempt += 1) {
      index = await page.locator('.my-hub-v41-news-row .news-v412-summary:not(.is-loading)').evaluateAll((boxes) => {
        return boxes.findIndex((box) => {
          const text = box.querySelector('.news-v417-summary-text');
          return text && text.textContent.trim().length > 0 && text.scrollHeight > text.clientHeight + 2;
        });
      });
      if (index < 0) await page.waitForTimeout(500);
    }
    assert.ok(index >= 0, 'No naturally clipped live MY-news summary was available to validate');

    const box = page.locator('.my-hub-v41-news-row .news-v412-summary:not(.is-loading)').nth(index);
    const before = await box.evaluate((node) => {
      const text = node.querySelector('.news-v417-summary-text');
      const row = node.closest('.my-hub-v41-news-row');
      const style = getComputedStyle(text);
      return {
        text: text.textContent.trim(),
        clientHeight: text.clientHeight,
        scrollHeight: text.scrollHeight,
        clamp: style.webkitLineClamp,
        overflow: style.overflow,
        rowClientHeight: row?.clientHeight || 0,
        rowScrollHeight: row?.scrollHeight || 0,
      };
    });
    assert.ok(before.scrollHeight > before.clientHeight + 2, `Expected clipped summary before expansion: ${JSON.stringify(before)}`);

    await box.click();
    await page.waitForFunction((idx) => {
      const boxes = [...document.querySelectorAll('.my-hub-v41-news-row .news-v412-summary:not(.is-loading)')];
      return boxes[idx]?.getAttribute('aria-expanded') === 'true';
    }, index);

    const after = await box.evaluate((node) => {
      const text = node.querySelector('.news-v417-summary-text');
      const row = node.closest('.my-hub-v41-news-row');
      const style = getComputedStyle(text);
      return {
        ariaExpanded: node.getAttribute('aria-expanded'),
        buttonText: node.querySelector('.news-v417-summary-head i')?.textContent?.trim(),
        clientHeight: text.clientHeight,
        scrollHeight: text.scrollHeight,
        clamp: style.webkitLineClamp,
        overflow: style.overflow,
        display: style.display,
        rowClientHeight: row?.clientHeight || 0,
        rowScrollHeight: row?.scrollHeight || 0,
      };
    });

    assert.equal(after.ariaExpanded, 'true');
    assert.equal(after.buttonText, '접기');
    assert.ok(after.clientHeight >= after.scrollHeight - 1, `Expanded summary remains clipped: ${JSON.stringify(after)}`);
    assert.ok(after.rowClientHeight >= after.rowScrollHeight - 1, `Expanded MY-news row remains clipped: ${JSON.stringify(after)}`);
    assert.deepEqual(errors, [], errors.join('\n'));
    console.log('LIVE_NEWS_EXPAND_PASS', JSON.stringify({ before: { ...before, text: before.text.slice(0, 180) }, after }));
  } finally {
    await context.close();
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});