const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const base = process.env.APP_URL || 'http://127.0.0.1:8080';
const json = value => ({ contentType: 'application/json', body: JSON.stringify(value) });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

const watchlist = [
  ['005930.KS','삼성전자'], ['000660.KS','SK하이닉스'], ['005380.KS','현대차'], ['035420.KS','NAVER'],
  ['AAPL','애플'], ['NVDA','엔비디아'], ['MSFT','마이크로소프트'], ['GOOGL','알파벳'],
  ['AMZN','아마존'], ['META','메타'], ['TSLA','테슬라'], ['AMD','AMD'],
].map(([symbol,name]) => ({symbol,name}));

const heatRows = [
  ['005930.KS',279750,1.11,500], ['000660.KS',1881000,-0.22,350], ['005380.KS',300000,0.55,80],
  ['000270.KS',140000,-0.7,70], ['373220.KS',400000,-0.8,60], ['035420.KS',300000,2.0,55],
  ['068270.KS',210000,-1.1,50], ['207940.KS',1200000,-0.4,90],
  ['NVDA',227.38,2.3,5490], ['AAPL',337.48,0.85,4950], ['MSFT',501.61,1.59,3720],
  ['GOOGL',354.97,1.55,4340], ['AMZN',250.45,1.87,2500], ['TSM',445.14,2.41,2200],
  ['META',741.25,11.43,1900], ['AVGO',375.30,1.6,1700], ['TSLA',420.00,3.03,1400], ['AMD',220.00,9.95,350],
].map(([ticker,price,change,marketCap]) => ({ticker,price,change,marketCap,asOf:'2026-09-22T06:30:00Z'}));

const staleHeat = {
  generatedAt: '2026-09-22T05:00:00Z',
  results: heatRows.map(row => ({...row, change: -9.99, price: Number(row.price) - 1})),
};

const freshSnapshot = {
  generatedAt: '2026-09-22T06:30:00Z',
  source: 'test',
  heatmap: {results: heatRows},
  macro: {summary:{text:'테스트 시장',level:'green'},results:[],staleCount:0},
};

(async () => {
  const browser = await chromium.launch();
  try {
    for (const profile of [
      {name:'mobile', viewport:{width:390,height:824}, isMobile:true, hasTouch:true},
      {name:'desktop', viewport:{width:1280,height:900}, isMobile:false, hasTouch:false},
    ]) {
      const context = await browser.newContext({
        viewport: profile.viewport,
        isMobile: profile.isMobile,
        hasTouch: profile.hasTouch,
        timezoneId:'Asia/Seoul',
        locale:'ko-KR',
      });
      const page = await context.newPage();
      const bootstrapRequests = [];
      const homeLiveRequests = [];

      await page.addInitScript(({watchlist, staleHeat}) => {
        localStorage.setItem('chartview-watchlist-v1', JSON.stringify(watchlist));
        localStorage.setItem('chartview-home-heatmap-v64', JSON.stringify(staleHeat));
        localStorage.removeItem('chartview-home-snapshot-v17');
        const now = Date.now();
        const quotes = {};
        for (const row of watchlist) {
          quotes[row.symbol] = {
            price: 100,
            return: 5,
            returnUpdatedAt: now,
            updatedAt: now,
          };
        }
        localStorage.setItem('chartview-watchlist-quotes-v33', JSON.stringify({updatedAt:now,quotes}));
      }, {watchlist, staleHeat});

      await page.route('**/api/home-snapshot*', route => route.fulfill(json(freshSnapshot)));
      await page.route('**/api/heatmap*', async route => {
        await delay(3000);
        await route.fulfill(json({results:heatRows,generatedAt:freshSnapshot.generatedAt,source:'test'}));
      });
      await page.route('**/api/quotes?*', route => {
        const req = route.request();
        const url = new URL(req.url());
        const symbols = (url.searchParams.get('tickers') || '').split(',').filter(Boolean);
        const mode = req.headers()['x-chartview-quote-mode'] || '';
        if (mode === 'watchlist-bootstrap-v64') bootstrapRequests.push(symbols);
        if (mode === 'home-major-live-v65') homeLiveRequests.push(symbols);
        return route.fulfill(json({
          fetchedAt:'2026-09-22T06:31:00Z',
          results:symbols.map((ticker,index) => ({
            ticker,
            price:100 + index,
            change:1.23,
            currency:/\.(KS|KQ)$/.test(ticker)?'KRW':'USD',
            asOf:'2026-09-22T06:31:00Z',
            source:'test quote',
            marketStatus:/\.(KS|KQ)$/.test(ticker)?'OPEN':'CLOSED',
            delayTime:0,
          })),
          errors:[],
        }));
      });
      await page.route('**/api/market-now*', route => route.fulfill(json({results:[],errors:[]})));
      await page.route('**/api/valuation?*', route => route.fulfill(json({stocks:[]})));
      await page.route('**/api/consensus?*', route => route.fulfill(json({periods:{},history:{}})));
      await page.route('**/api/personalized-news?*', route => route.fulfill(json({items:[],groups:[],errors:[]})));
      await page.route('**/api/compare?*', route => {
        const symbols = (new URL(route.request().url()).searchParams.get('tickers') || '').split(',').filter(Boolean);
        return route.fulfill(json({stocks:symbols.map(ticker => ({ticker,price:100,return:5,data:[{time:1,value:0},{time:2,value:5}]})),errors:[]}));
      });

      const response = await page.goto(base, {waitUntil:'domcontentloaded',timeout:60000});
      assert.equal(response.status(), 200, profile.name);
      await page.locator('#home-tab.active').waitFor({timeout:30000});

      // Heatmap must synchronize from the fresh Home snapshot without waiting for delayed /api/heatmap.
      const samsungChange = page.locator('[data-cvhm-symbol="005930.KS"] .cvhm-change');
      await samsungChange.waitFor({timeout:1500});
      assert.equal((await samsungChange.textContent()).trim(), '+1.11%', `${profile.name}: heatmap used stale private cache`);

      // A single fast quote batch must drive both Card and Heatmap to the exact same live value.
      await page.waitForFunction(() => window.ChartViewHomeHeatmap?.version === 'v65', null, {timeout:5000});
      await page.waitForFunction(() => {
        const card = document.querySelector('.home16-stock[data-home-symbol="005930.KS"] b');
        const heat = document.querySelector('[data-cvhm-symbol="005930.KS"] .cvhm-change');
        return card?.textContent?.trim() === '+1.23%' && heat?.textContent?.trim() === '+1.23%';
      }, null, {timeout:5000});
      assert.ok(homeLiveRequests.length >= 1, `${profile.name}: missing Home all-symbol live quote request`);
      assert.equal(new Set(homeLiveRequests[0]).size, 18, `${profile.name}: initial Home live request did not cover all heatmap symbols`);

      // Enter Watchlist and verify one all-symbol lightweight bootstrap irrespective of viewport size.
      await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
      await page.locator('#watchlist-tab.active').waitFor({timeout:10000});
      await page.waitForFunction(() => document.querySelectorAll('[data-watch-card]').length === 12, null, {timeout:10000});
      await page.waitForFunction(() => document.querySelectorAll('[data-watch-live-line]').length === 12, null, {timeout:10000});
      await page.waitForFunction(() => [...document.querySelectorAll('[data-live-day-change]')].every(el => el.textContent.includes('+1.23%')), null, {timeout:10000});
      await page.waitForFunction(() => window.ChartViewLiveQuotes?.version === 'v64', null, {timeout:5000});

      assert.ok(bootstrapRequests.length >= 1, `${profile.name}: missing watchlist all-symbol bootstrap`);
      assert.equal(new Set(bootstrapRequests[0]).size, 12, `${profile.name}: bootstrap did not include all watchlist symbols`);
      assert.equal(await page.locator('[data-watch-live-line]').count(), 12, `${profile.name}: today rows missing`);

      await context.close();
    }
  } finally {
    await browser.close();
  }
  console.log('cross-device V65 quote parity OK');
})().catch(err => {
  console.error(err);
  process.exit(1);
});
