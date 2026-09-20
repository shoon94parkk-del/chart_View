const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function fn(file,name){const code=fs.readFileSync(file,'utf8');const start=code.indexOf('function '+name+'(');assert.ok(start>=0,`${name} is available`);const end=code.indexOf('\n  }',start)+4;return vm.runInNewContext('('+code.slice(start,end)+')');}
test('quote time uses quote timestamp, never the chart end date',()=>{const get=fn('static/js/single_detail_v40.js','quotePresentation');const q=get({price:208500,quoteAsOf:'2026-09-18T20:20:20+09:00',quoteSource:'Naver',endDate:'2026-09-18'},{});assert.equal(q.asOf,'2026-09-18T20:20:20+09:00');assert.equal(q.source,'Naver');assert.equal(get({price:1,endDate:'2026-09-18'},{}).asOf,'');});
test('screener stats exclude missing daily changes and use filtered rows',()=>{const get=fn('static/js/screener.js','summarizeRows');const q=get([{change1d:5,rsi14:30,volumeRatio:3},{change1d:-2,rsi14:50,volumeRatio:1},{change1d:null,rsi14:null,volumeRatio:null}]);assert.equal(q.upRate,50);assert.equal(q.total,3);assert.equal(q.rsi35,1);assert.equal(q.volume2x,1);});
