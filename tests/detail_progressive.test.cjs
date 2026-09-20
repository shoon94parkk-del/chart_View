// Run with jsdom installed: NODE_PATH=<test dependencies>/node_modules node --test tests/detail_progressive.test.cjs
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const fs=require('node:fs');
const flush=()=>new Promise(r=>setImmediate(r));
test('detail paints chart before slow fundamentals, handles retry and ignores obsolete period responses',async()=>{
 const dom=new JSDOM('<div id="chart-tab" class="tab-content active"></div>',{url:'https://chart.test/',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window, pending=[];
 w.HTMLElement.prototype.scrollIntoView=()=>{}; w.scrollTo=()=>{};
 w.fetch=(url)=>new Promise(resolve=>pending.push({url,resolve}));
 w.eval(fs.readFileSync('static/js/app_state_v40.js','utf8'));
 w.__openAppTab=()=>{};
 w.eval(fs.readFileSync('static/js/single_detail_v40.js','utf8'));
 const reply=(request,data,ok=true)=>request.resolve({ok,status:ok?200:503,json:async()=>data});
 const chart=(value)=>({stocks:[{ticker:'TEST',price:208500,quoteAsOf:'2026-09-18T20:20:20+09:00',quoteSource:'Naver',return:value,data:[{time:1,value:0},{time:2,value}],endDate:'2026-09-18',priceBasis:'adjusted_close'}]});
 try {
  await w.__openStockDetail('TEST','Test');assert.equal(pending.length,3);
  reply(pending[0],chart(2));await flush();await flush();
  assert.match(w.document.querySelector('.detail-v40-price').textContent,/20:20/);
  assert.ok(w.document.querySelector('[data-detail-chart-readout]'));
  assert.match(w.document.body.textContent,/재무 불러오는 중/);
  w.document.querySelector('[data-detail-tab="value"]').click();
  reply(pending[1],{},false);await flush();await flush();
  assert.equal(w.document.querySelector('[data-detail-panel="value"]').hidden,false);
  assert.match(w.document.querySelector('.detail-v40-value-list').textContent,/조회 실패/);
  w.document.querySelector('[data-detail-retry-source="valuation"]').click();
  reply(pending[3],{stocks:[{price:208500,forwardPE:null,trailingPE:10}]});await flush();await flush();
  assert.match(w.document.querySelector('.detail-v40-value-list').textContent,/미제공/);
  w.document.querySelector('[data-detail-tab="chart"]').click();
  w.document.querySelector('[data-detail-period="3mo"]').click();
  w.document.querySelector('[data-detail-period="1y"]').click();
  const a=pending.find(x=>x.url.includes('period=3mo')), b=pending.find(x=>x.url.includes('period=1y'));
  reply(b,chart(20));await flush();await flush();reply(a,chart(3));await flush();await flush();
  assert.match(w.document.querySelector('.detail-v40-metrics').textContent,/20/);
  assert.equal(w.document.querySelector('[data-detail-period="1y"]').getAttribute('aria-pressed'),'true');
  reply(pending[2],{});await flush();await flush();
  w.__closeStockDetail({force:true,restore:false});
  assert.equal(w.document.getElementById('stock-detail-v40').hidden,true);
 }finally {dom.window.close();}
});
