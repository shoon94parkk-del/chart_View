// Browser regressions run in CI in an isolated context; no saved user state is used.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.APP_URL || 'http://127.0.0.1:8080';
const live = process.env.LIVE === '1';
const json = value => ({ contentType: 'application/json', body: JSON.stringify(value) });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  fs.mkdirSync('test-results', { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const width of [360, 384, 430]) {
      const context = await browser.newContext({
        viewport: { width, height: 824 }, isMobile: true, hasTouch: true,
        timezoneId: 'Asia/Seoul', locale: 'ko-KR',
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      if (!live) {
        const disk = JSON.parse(fs.readFileSync('static/data/valuation_cache.json'));
        const quotes = Object.entries(disk.quotes).map(([ticker, q]) => ({ ticker, name: q.shortName, price: q.regularMarketPrice, change: 1, asOf: disk.generatedAt }));
        await page.route('**/api/home-snapshot*', r => r.fulfill(json({heatmap:{results:quotes}, generatedAt:disk.generatedAt})));
        await page.route('**/api/market-now*', r => r.fulfill(json({results:[], errors:[]})));
        await page.route('**/api/valuation?*', r => r.fulfill(json({stocks:[]})));
        await page.route('**/api/consensus?*', r => r.fulfill(json({periods:{}, history:{}})));
        await page.route('**/api/personalized-news?*', r => r.fulfill(json({items:[],groups:[],errors:[]})));
        await page.route('**/api/compare?*', r => {
          const symbols = new URL(r.request().url()).searchParams.get('tickers').split(',');
          return r.fulfill(json({stocks:symbols.map(ticker => ({ticker,name:ticker,price:100,return:10,actualStart:'2026-08-12',actualEnd:'2026-09-11',data:[{time:1788825600,value:0},{time:1788912000,value:10}]})),errors:[]}));
        });
      }
      const response = await page.goto(base, {waitUntil:'domcontentloaded',timeout:60000});
      assert.equal(response.status(), 200);
      await page.locator('.app-bottom-nav').waitFor({timeout:30000});
      await page.locator('#home-watchlist-v30').waitFor({timeout:30000});
      await page.locator('#home-watchlist-v30').getByText('MY STOCKS · 1달 수익률').waitFor();
      await page.screenshot({path:`test-results/${width}-home.png`,fullPage:true});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}: home overflow`);
      await page.locator('.app-bottom-btn[data-app-mode="analysis"]').click();
      await page.locator('#chart-tab.active').waitFor();
      await page.locator('#legend .legend-item').first().waitFor({timeout:60000});
      assert.equal(await page.locator('#stock-brief-v8').evaluate(el => getComputedStyle(el).display), 'none');
      const metrics = await page.evaluate(() => ({
        width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
        navCount:document.querySelectorAll('.app-bottom-btn').length,
        navRows:new Set([...document.querySelectorAll('.app-bottom-btn')].map(x=>Math.round(x.getBoundingClientRect().top))).size,
        dates:getComputedStyle(document.getElementById('custom-date-fields')).display,
        chartTop:Math.round(document.getElementById('chart-container').getBoundingClientRect().top),
      }));
      assert(metrics.scrollWidth <= width, `${width}: analysis overflow`);
      assert.equal(metrics.navCount,5); assert.equal(metrics.navRows,1);
      assert.equal(metrics.dates,'none'); assert(metrics.chartTop <= 420, `${width}: chart top ${metrics.chartTop}`);
      const ytdRequest = page.waitForRequest(r => r.url().includes('/api/compare?') && new URL(r.url()).searchParams.has('start'));
      await page.locator('.period-chip[data-period="ytd"]').click();
      const ytd = new URL((await ytdRequest).url());
      assert.equal(ytd.searchParams.get('start'),`${new Date().getFullYear()}-01-01`);
      await page.screenshot({path:`test-results/${width}-analysis.png`,fullPage:true});
      await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').click();
      await page.locator('#watchlist-tab.active').waitFor();
      await page.locator('.app-bottom-btn[data-app-mode="discover"]').click();
      await page.locator('#screener-tab.active').waitFor();
      await page.locator('.app-bottom-btn[data-app-mode="market"]').click();
      await page.locator('#macro-tab.active').waitFor();
      await page.locator('.app-bottom-btn[data-app-mode="analysis"]').click();
      await page.locator('#chart-tab.active').waitFor();
      if (width === 384) {
        // Simulate provider failure only inside this test browser; verify recovery UX.
        await page.route('**/api/compare?*', r => r.fulfill({status:503,...json({error:'test unavailable'})}));
        await page.locator('.period-chip[data-period="3mo"]').click();
        await page.locator('#chart-status').getByText('다시 시도',{exact:true}).waitFor();
        assert.equal(await page.locator('#legend .legend-item').count(),0);
        await page.screenshot({path:'test-results/384-chart-retry.png',fullPage:true});
      }
      assert.equal(errors.length,0,errors.join('\n'));
      console.log('MOBILE_PASS',JSON.stringify({...metrics,live}));
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
