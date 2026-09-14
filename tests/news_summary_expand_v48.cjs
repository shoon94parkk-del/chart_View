const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const BASE = process.env.APP_URL || 'http://127.0.0.1:8080';
const LONG_SUMMARY = '델은 AI 인프라 고객사의 대규모 자금조달과 서버 수요 확대에 노출되어 있습니다. 이번 기사에서는 약 35억달러 규모의 자금조달 논의와 공급 관계를 설명하고 있으며, 자금조달 성사 여부가 델의 실제 매출 인식으로 바로 이어지는 것은 아니라는 점도 함께 짚고 있습니다. 따라서 투자자는 고객사의 자금 확보, 발주 전환, 실제 매출 인식 시점을 구분해서 확인할 필요가 있습니다.';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ko-KR' });
  await context.addInitScript(() => {
    localStorage.setItem('chartview-watchlist-v1', JSON.stringify([{ symbol: 'DELL', name: '델' }]));
  });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);

  const item = {
    symbol: 'DELL', name: '델', title: 'Dell AI infrastructure funding story', source: 'Test News',
    publishedAt: new Date().toISOString(), publishedTs: Date.now(), url: 'https://example.com/dell', score: 200,
    relationType: 'direct', relationBasis: '제목에 기업명 확인', summarySeed: 'Dell AI funding relationship summary seed'
  };
  const payload = { items: [item], errors: [], groups: [{ symbol: 'DELL', name: '델', status: 'success', items: [item] }] };

  await page.route('**/api/personalized-news?**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) }));
  await page.route('**/api/news-summary?**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ titleKo: '델 AI 인프라 자금조달 기사', summary: LONG_SUMMARY, basis: 'snippet', basisLabel: '기사 요약문 기반' }) }));

  try {
    await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
    await page.waitForSelector('#watchlist-tab[data-my-hub-version]');
    await page.locator('[data-v41-view="news"]').click();
    const box = page.locator('.my-hub-v41-news-row .news-v412-summary').first();
    const text = box.locator('.news-v417-summary-text');
    await text.waitFor({ state: 'visible' });
    await page.waitForFunction((expected) => document.querySelector('.my-hub-v41-news-row .news-v417-summary-text')?.textContent === expected, LONG_SUMMARY);

    const before = await text.evaluate(el => ({ clientHeight: el.clientHeight, scrollHeight: el.scrollHeight, display: getComputedStyle(el).display }));
    assert.ok(before.scrollHeight > before.clientHeight + 4, `summary should start collapsed: ${JSON.stringify(before)}`);

    await box.click();
    await page.waitForFunction(() => document.querySelector('.my-hub-v41-news-row .news-v412-summary')?.getAttribute('aria-expanded') === 'true');
    assert.equal((await box.locator('.news-v417-summary-head i').innerText()).trim(), '접기');

    const after = await text.evaluate(el => ({ clientHeight: el.clientHeight, scrollHeight: el.scrollHeight, display: getComputedStyle(el).display, overflow: getComputedStyle(el).overflow, clamp: getComputedStyle(el).webkitLineClamp }));
    assert.ok(after.clientHeight > before.clientHeight + 10, `expanded summary should grow: before=${JSON.stringify(before)} after=${JSON.stringify(after)}`);
    assert.ok(after.clientHeight >= after.scrollHeight - 1, `expanded summary must reveal all text: ${JSON.stringify(after)}`);
    assert.notEqual(after.clamp, '2', `expanded summary must remove two-line clamp: ${JSON.stringify(after)}`);

    console.log('NEWS_SUMMARY_EXPAND_V48_PASS', JSON.stringify({ before, after }));
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
