// Historical PER/PBR valuation bands. Loaded after fwdper.js.
(() => {
  'use strict';

  let bandMetric = 'per';
  let bandTicker = null;
  let bandPayload = null;
  let bandChart = null;
  let resizeObserver = null;
  let requestController = null;
  let requestSeq = 0;

  const css = `
    .band-section{display:none;margin:16px 20px 24px;background:#fff;border:1px solid #eaedf0;border-radius:18px;padding:20px;box-shadow:0 2px 12px rgba(0,0,0,.035)}
    .band-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}
    .band-title{font-size:20px;font-weight:800;color:#191f28;margin:0 0 5px}.band-desc{font-size:13px;color:#6b7684;line-height:1.5;margin:0}
    .band-stock-tabs,.band-metric-tabs{display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}.band-stock-tabs::-webkit-scrollbar,.band-metric-tabs::-webkit-scrollbar{display:none}
    .band-stock-tabs{margin:14px 0 10px}.band-stock-btn,.band-metric-btn{border:1px solid #e5e8eb;background:#fff;color:#4e5968;border-radius:999px;padding:9px 12px;font-size:13px;font-weight:700;white-space:nowrap;cursor:pointer}
    .band-stock-btn.active,.band-metric-btn.active{background:#191f28;color:#fff;border-color:#191f28}.band-metric-tabs{margin:0 0 14px}.band-metric-btn{min-width:92px}
    .band-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin:0 0 14px}.band-card{background:#f7f8fa;border-radius:13px;padding:12px}.band-card span{display:block;color:#8b95a1;font-size:11px;margin-bottom:5px}.band-card strong{display:block;color:#191f28;font-size:17px;line-height:1.2}.band-card small{display:block;color:#6b7684;font-size:10px;margin-top:4px;line-height:1.3}
    .band-chart-wrap{position:relative;border:1px solid #edf0f2;border-radius:14px;overflow:hidden;background:#fff}.band-chart{height:340px;width:100%}.band-loading{height:340px;display:flex;align-items:center;justify-content:center;color:#8b95a1;font-size:13px}.band-foot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:#8b95a1;font-size:11px;line-height:1.45;margin-top:10px}.band-legend{display:flex;gap:10px;flex-wrap:wrap}.band-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}.band-note{margin-top:10px;padding:10px 12px;border-radius:12px;background:#f7f8fa;color:#4e5968;font-size:12px;line-height:1.5}.band-empty{padding:34px 14px;text-align:center;color:#8b95a1;font-size:13px}
    @media(max-width:720px){.band-section{margin:10px 8px 18px;padding:14px;border-radius:16px}.band-head{display:block}.band-title{font-size:18px}.band-cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.band-card{padding:10px}.band-card strong{font-size:16px}.band-chart{height:300px}.band-loading{height:300px}.band-stock-btn,.band-metric-btn{min-height:40px;padding:9px 13px}.band-foot{display:block}.band-legend{margin-bottom:5px}}
  `;

  function injectStyles(){
    if(document.getElementById('valuation-band-style')) return;
    const style=document.createElement('style');style.id='valuation-band-style';style.textContent=css;document.head.appendChild(style);
  }

  const esc=(v)=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
  const fmt=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}):'-';
  function tickers(){return (typeof perTickers!=='undefined'&&Array.isArray(perTickers))?[...perTickers]:[];}
  function nameOf(t){try{return (typeof perTickerNameMap!=='undefined'&&perTickerNameMap[t])||t;}catch{return t;}}

  function install(){
    injectStyles();
    const metricRow=document.querySelector('.metric-chips');
    const perSection=document.querySelector('#fwdper-tab .per-section');
    if(!metricRow||!perSection||document.querySelector('[data-metric="bands"]')) return;

    const chip=document.createElement('button');
    chip.className='metric-chip';chip.dataset.metric='bands';chip.textContent='📈 역사적 밸류 밴드';
    const pbrChip=metricRow.querySelector('[data-metric="pbr"]');
    if(pbrChip) pbrChip.insertAdjacentElement('afterend',chip); else metricRow.appendChild(chip);

    const section=document.createElement('section');
    section.id='valuation-band-section';section.className='band-section';
    section.innerHTML=`
      <div class="band-head"><div><h2 class="band-title">역사적 밸류에이션 밴드</h2><p class="band-desc">현재 PER·PBR이 자기 과거 범위에서 어느 위치인지 비교합니다. 데이터가 확보되는 최근 3년을 기준으로 재구성합니다.</p></div></div>
      <div id="band-stock-tabs" class="band-stock-tabs"></div>
      <div class="band-metric-tabs"><button class="band-metric-btn active" data-band-metric="per">TTM PER</button><button class="band-metric-btn" data-band-metric="pbr">PBR</button></div>
      <div id="band-cards" class="band-cards"></div>
      <div class="band-chart-wrap"><div id="band-chart" class="band-chart"></div><div id="band-loading" class="band-loading" style="display:none">밸류 밴드를 계산하는 중...</div></div>
      <div class="band-foot"><div class="band-legend"><span><i class="band-dot" style="background:#3182f6"></i>역사적 값</span><span><i class="band-dot" style="background:#00a86b"></i>20% 구간</span><span><i class="band-dot" style="background:#8b95a1"></i>중앙값</span><span><i class="band-dot" style="background:#f04452"></i>80% 구간</span></div><span id="band-range"></span></div>
      <div id="band-note" class="band-note">과거 재무값을 현재 값처럼 소급 적용하지 않습니다.</div>`;
    perSection.insertAdjacentElement('afterend',section);

    chip.addEventListener('click',(ev)=>{ev.preventDefault();activateBands();});
    metricRow.querySelectorAll('.metric-chip:not([data-metric="bands"])').forEach(btn=>btn.addEventListener('click',()=>deactivateBands()));
    section.querySelectorAll('[data-band-metric]').forEach(btn=>btn.addEventListener('click',()=>{
      section.querySelectorAll('[data-band-metric]').forEach(b=>b.classList.remove('active'));btn.classList.add('active');bandMetric=btn.dataset.bandMetric;render();
    }));

    const tags=document.getElementById('ticker-tags');
    if(tags){let timer=null;new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>{renderTickerTabs();if(section.style.display!=='none') ensureTickerAndLoad();},100);}).observe(tags,{childList:true,subtree:true});}
  }

  function activateBands(){
    document.querySelectorAll('.metric-chip').forEach(b=>b.classList.toggle('active',b.dataset.metric==='bands'));
    const per=document.querySelector('#fwdper-tab .per-section');if(per) per.style.display='none';
    const section=document.getElementById('valuation-band-section');if(section)section.style.display='block';
    renderTickerTabs();ensureTickerAndLoad();
  }
  function deactivateBands(){
    const per=document.querySelector('#fwdper-tab .per-section');if(per) per.style.display='block';
    const section=document.getElementById('valuation-band-section');if(section)section.style.display='none';
  }

  function renderTickerTabs(){
    const el=document.getElementById('band-stock-tabs');if(!el)return;
    const list=tickers();
    if(!list.length){el.innerHTML='';bandTicker=null;return;}
    if(!bandTicker||!list.includes(bandTicker)) bandTicker=list[0];
    el.innerHTML=list.map(t=>`<button class="band-stock-btn ${t===bandTicker?'active':''}" data-band-ticker="${esc(t)}">${esc(nameOf(t))}</button>`).join('');
    el.querySelectorAll('[data-band-ticker]').forEach(btn=>btn.addEventListener('click',()=>{bandTicker=btn.dataset.bandTicker;renderTickerTabs();load();}));
  }

  function ensureTickerAndLoad(){
    const list=tickers();
    if(!list.length){bandTicker=null;bandPayload=null;destroyChart();document.getElementById('band-cards').innerHTML='';document.getElementById('band-chart').innerHTML='<div class="band-empty">상단에서 종목을 먼저 선택해 주세요.</div>';return;}
    if(!bandTicker||!list.includes(bandTicker)) bandTicker=list[0];
    load();
  }

  async function load(){
    if(!bandTicker)return;
    const seq=++requestSeq;if(requestController)requestController.abort();requestController=new AbortController();
    const loading=document.getElementById('band-loading'),chartEl=document.getElementById('band-chart');
    if(loading)loading.style.display='flex';if(chartEl)chartEl.style.visibility='hidden';
    try{
      const r=await fetch(`/api/valuation-band?ticker=${encodeURIComponent(bandTicker)}&years=3`,{cache:'no-store',signal:requestController.signal});
      if(!r.ok){let msg='';try{msg=(await r.json()).error||'';}catch{}throw new Error(msg||`HTTP ${r.status}`);}
      const data=await r.json();if(seq!==requestSeq)return;bandPayload=data;render();
    }catch(e){if(e?.name==='AbortError')return;console.error('valuation band error',e);bandPayload=null;destroyChart();if(chartEl){chartEl.style.visibility='visible';chartEl.innerHTML=`<div class="band-empty">${esc(e.message||'역사적 밸류 데이터를 불러오지 못했습니다.')}</div>`;}document.getElementById('band-cards').innerHTML='';}
    finally{if(seq===requestSeq){if(loading)loading.style.display='none';if(chartEl)chartEl.style.visibility='visible';}}
  }

  function destroyChart(){if(resizeObserver){resizeObserver.disconnect();resizeObserver=null;}if(bandChart){try{bandChart.remove();}catch{}bandChart=null;}}

  function render(){
    if(!bandPayload)return;
    const pack=bandPayload[bandMetric];const cards=document.getElementById('band-cards'),range=document.getElementById('band-range'),note=document.getElementById('band-note');
    if(!pack?.stats||!Array.isArray(pack.points)||!pack.points.length){destroyChart();cards.innerHTML='';document.getElementById('band-chart').innerHTML='<div class="band-empty">이 종목은 해당 역사적 지표 데이터가 충분하지 않습니다.</div>';if(range)range.textContent='';return;}
    const s=pack.stats;
    cards.innerHTML=`
      <div class="band-card"><span>현재 ${bandMetric.toUpperCase()}</span><strong>${fmt(s.current)}x</strong><small>${esc(s.label)}</small></div>
      <div class="band-card"><span>3년 중앙값</span><strong>${fmt(s.median)}x</strong><small>평균 ${fmt(s.mean)}x</small></div>
      <div class="band-card"><span>현재 백분위</span><strong>${fmt(s.percentile,1)}%</strong><small>낮을수록 과거 대비 저평가</small></div>
      <div class="band-card"><span>20~80% 밴드</span><strong>${fmt(s.p20)} ~ ${fmt(s.p80)}</strong><small>${s.observations}주 관측치</small></div>`;
    if(range)range.textContent=`${s.start} ~ ${s.end}`;
    if(note)note.textContent=`${bandPayload.method} · ${bandPayload.source}. 밴드는 상대적 위치이며 저평가/고평가만으로 매수·매도를 뜻하지 않습니다.`;
    draw(pack);
  }

  function draw(pack){
    const el=document.getElementById('band-chart');if(!el||!window.LightweightCharts)return;destroyChart();el.innerHTML='';
    bandChart=LightweightCharts.createChart(el,{width:el.clientWidth,height:el.clientHeight||340,layout:{background:{type:LightweightCharts.ColorType.Solid,color:'#ffffff'},textColor:'#6b7684'},grid:{vertLines:{color:'#f2f4f6'},horzLines:{color:'#f2f4f6'}},rightPriceScale:{borderVisible:false},timeScale:{borderVisible:false,timeVisible:false},crosshair:{mode:LightweightCharts.CrosshairMode.Normal}});
    const series=bandChart.addLineSeries({color:'#3182f6',lineWidth:2,priceLineVisible:false,lastValueVisible:true});
    series.setData(pack.points.map(p=>({time:p.time,value:Number(p.value)})));
    const s=pack.stats;
    if(Number.isFinite(Number(s.p20)))series.createPriceLine({price:Number(s.p20),color:'#00a86b',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:true,title:'20%'});
    if(Number.isFinite(Number(s.median)))series.createPriceLine({price:Number(s.median),color:'#8b95a1',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dotted,axisLabelVisible:true,title:'중앙'});
    if(Number.isFinite(Number(s.p80)))series.createPriceLine({price:Number(s.p80),color:'#f04452',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:true,title:'80%'});
    bandChart.timeScale().fitContent();
    resizeObserver=new ResizeObserver(()=>{if(bandChart&&el.clientWidth>0)bandChart.applyOptions({width:el.clientWidth,height:el.clientHeight||340});});resizeObserver.observe(el);
  }

  document.addEventListener('DOMContentLoaded',install);
})();
