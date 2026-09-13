const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const BASE = process.env.APP_URL || 'http://127.0.0.1:8080';
const watch = [{symbol:'NVDA',name:'엔비디아'},{symbol:'AAPL',name:'애플'}];
const shared = {symbol:'NVDA',name:'엔비디아',title:'NVIDIA and Apple expand AI supply agreement',source:'Test',publishedAt:new Date().toISOString(),publishedTs:Date.now(),url:'https://example.com/shared',score:180,relationType:'direct',relationBasis:'제목에 기업명·티커 확인'};
const payload = {items:[shared],errors:[],groups:[{symbol:'NVDA',name:'엔비디아',status:'success',items:[shared]},{symbol:'AAPL',name:'애플',status:'success',items:[{...shared,symbol:'AAPL',name:'애플',relationType:'direct'}]}]};
const valuationStocks = [
 {ticker:'AAPL',name:'Apple',price:250.15,forwardPE:28.4,trailingPE:31.2,pbr:45.1,psr:10.4,evEbitda:22.1,roe:158.2,operatingMargin:31.5,dividendYield:0.4},
 {ticker:'NVDA',name:'NVIDIA',price:190.8,forwardPE:34.1,trailingPE:41.7,pbr:39.2,psr:20.3,evEbitda:31.8,roe:112.3,operatingMargin:62.1,dividendYield:0.1},
 {ticker:'005930.KS',name:'삼성전자',price:266000,forwardPE:12.8,trailingPE:16.4,pbr:1.8,psr:2.2,evEbitda:8.7,roe:12.4,operatingMargin:14.8,dividendYield:1.5},
];
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 await context.addInitScript(rows=>localStorage.setItem('chartview-watchlist-v1',JSON.stringify(rows)),watch);
 const page=await context.newPage(); page.setDefaultTimeout(15000);
 let failNews=false; let delayNews=false;
 await page.route('**/api/personalized-news?**',async route=>{ if(delayNews) await new Promise(r=>setTimeout(r,1400)); if(failNews) return route.fulfill({status:500,body:'fail'}); return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)}); });
 await page.route('**/api/compare?**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({stocks:[{ticker:'NVDA',price:100,return:-2.4,startDate:'2026-08-12',endDate:'2026-09-12',priceBasis:'adjusted_close',data:[{time:1754956800,value:0},{time:1755302400,value:2},{time:1755907200,value:-1},{time:1757376000,value:-2.4}]}]})}));
 await page.route('**/api/valuation?**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({stocks:valuationStocks})}));
 await page.route('**/api/consensus?**',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
 const errors=[]; page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(BASE,{waitUntil:'domcontentloaded'});
 await page.waitForSelector('.app-bottom-btn[data-app-mode="watchlist"]');

 // shared URL belongs to both filters but appears once in ALL.
 await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').tap();
 await page.waitForSelector('[data-v41-view="news"]'); await page.locator('[data-v41-view="news"]').tap();
 await page.waitForSelector('.my-hub-v41-news-row');
 assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);
 await page.locator('[data-v41-symbol="NVDA"]').tap(); assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);
 await page.locator('[data-v41-symbol="AAPL"]').tap(); assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);

 // successful receive timestamp does not change on filter/sort only.
 const received1=await page.evaluate(()=>window.__chartViewMyNewsState.receivedAt);
 await page.locator('[data-v41-sort="relevance"]').tap(); await page.waitForTimeout(100);
 const received2=await page.evaluate(()=>window.__chartViewMyNewsState.receivedAt); assert.equal(received2,received1);

 // failed refresh keeps data and interactions, reports stale, and keeps receivedAt.
 failNews=true; await page.locator('[data-v41-refresh]').tap();
 await page.waitForFunction(()=>window.__chartViewMyNewsState && !window.__chartViewMyNewsState.loading);
 assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);
 assert.match(await page.locator('[data-v41-status]').innerText(),/갱신에 실패/);
 assert.equal(await page.evaluate(()=>window.__chartViewMyNewsState.receivedAt),received1);
 const summary=page.locator('.my-hub-v41-news-row .news-v412-summary').first(); await summary.waitFor(); await summary.tap(); assert.equal(await summary.getAttribute('aria-expanded'),'true');

 // detail -> bottom navigation must close detail and remain on target after late detail work.
 failNews=false; await page.locator('.my-hub-v41-news-row [data-v41-detail]').tap(); await page.waitForSelector('#stock-detail-v40:not([hidden])');
 await page.locator('.app-bottom-btn[data-app-mode="home"]').tap(); await page.waitForSelector('#home-tab',{state:'visible'}); await page.waitForTimeout(2200);
 assert.equal(await page.locator('#stock-detail-v40').isVisible(),false); assert.ok(await page.locator('.app-bottom-btn[data-app-mode="home"]').evaluate(el=>el.classList.contains('active')));

 // stale request cannot repopulate an emptied watchlist.
 await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').tap(); await page.locator('[data-v41-view="news"]').tap(); delayNews=true;
 const refresh=page.locator('[data-v41-refresh]'); await refresh.tap();
 await page.evaluate(()=>{ localStorage.setItem('chartview-watchlist-v1','[]'); document.dispatchEvent(new CustomEvent('chartview:watchlist-change',{detail:{items:[]}})); });
 await page.waitForTimeout(1800);
 assert.equal(await page.locator('.my-hub-v41-news-row').count(),0); assert.equal(await page.evaluate(()=>window.__chartViewMyNewsState.key),'');

 // Mobile valuation must remain one-stock-per-card, not the legacy 588-608px matrix.
 await page.evaluate(()=>window.switchTab('fwdper'));
 await page.waitForSelector('#fwdper-tab.active .per-table tbody tr');
 await page.waitForFunction(()=>document.querySelector('#fwdper-tab .per-table tbody tr td:nth-child(2)')?.dataset.label === '현재가');
 const valuationLayout=await page.evaluate(()=>{
   const container=document.getElementById('per-table-container');
   const table=container.querySelector('.per-table');
   const row=table.querySelector('tbody tr');
   const first=row.children[0];
   const metric=row.children[1];
   const cr=container.getBoundingClientRect(), rr=row.getBoundingClientRect(), mr=metric.getBoundingClientRect();
   return {
     width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
     containerWidth:cr.width,rowWidth:rr.width,rowLeft:rr.left,rowRight:rr.right,containerLeft:cr.left,containerRight:cr.right,
     tableDisplay:getComputedStyle(table).display,theadDisplay:getComputedStyle(table.tHead).display,
     rowDisplay:getComputedStyle(row).display,firstPosition:getComputedStyle(first).position,
     metricDisplay:getComputedStyle(metric).display,metricRight:mr.right,
     labels:Array.from(row.children).slice(1).map(td=>td.dataset.label || ''),
   };
 });
 assert(valuationLayout.scrollWidth<=valuationLayout.width,`valuation overflow ${JSON.stringify(valuationLayout)}`);
 assert.equal(valuationLayout.tableDisplay,'block');
 assert.equal(valuationLayout.theadDisplay,'none');
 assert.equal(valuationLayout.rowDisplay,'block');
 assert.equal(valuationLayout.firstPosition,'static');
 assert.equal(valuationLayout.metricDisplay,'grid');
 assert(valuationLayout.rowWidth<=valuationLayout.containerWidth+1,`card wider than container ${JSON.stringify(valuationLayout)}`);
 assert(valuationLayout.rowLeft>=valuationLayout.containerLeft-1 && valuationLayout.rowRight<=valuationLayout.containerRight+1,`card escaped container ${JSON.stringify(valuationLayout)}`);
 assert(valuationLayout.labels.length>=4 && valuationLayout.labels.every(Boolean),`missing valuation labels ${JSON.stringify(valuationLayout.labels)}`);
 await page.screenshot({path:'test-results/390-valuation-cards.png',fullPage:true});

 assert.deepEqual(errors,[]);
 console.log('PRELAUNCH_V42_PASS'); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
