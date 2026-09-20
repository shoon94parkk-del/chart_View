const {test}=require('node:test');const assert=require('node:assert/strict');const {JSDOM}=require('jsdom');const fs=require('node:fs');
test('screener exposes every result and resets paging when filters change',async()=>{
 const dom=new JSDOM('<button data-tab="screener"></button><div id="screener-tab" class="active"></div>',{url:'https://chart.test',runScripts:'outside-only',pretendToBeVisual:true});const w=dom.window;
 w.HTMLElement.prototype.scrollIntoView=()=>{};w.scrollTo=()=>{};
 const stocks=Array.from({length:251},(_,i)=>({symbol:`${i}.KS`,code:String(i),name:`Stock ${i}`,market:i%2?'KOSDAQ':'KOSPI',score:30,price:100,change1d:i%2?-1:1,rsi14:50,volumeRatio:1}));
 w.fetch=async()=>({ok:true,json:async()=>({tradeDate:'2026-09-18',stocks})});
 try {w.eval(fs.readFileSync('static/js/screener.js','utf8'));w.document.dispatchEvent(new w.Event('DOMContentLoaded'));await w.__openScreenerAtTop();
 assert.equal(w.document.querySelectorAll('tbody tr').length,100);
 w.document.getElementById('screener-more').click();assert.equal(w.document.querySelectorAll('tbody tr').length,200);
 w.document.getElementById('screener-more').click();assert.equal(w.document.querySelectorAll('tbody tr').length,251);assert.ok(w.document.getElementById('screener-more').hidden);
 w.__setScreenerQuickFilter('up');assert.equal(w.document.querySelectorAll('tbody tr').length,100);assert.equal(w.__getScreenerStats().total,126);assert.equal(w.__getScreenerStats().upRate,100);
 }finally{dom.window.close();}
});
