// Phase 2: analyst EPS/revenue consensus trends for the valuation tab.
(() => {
  'use strict';

  let ticker = null;
  let period = '0y';
  let mode = 'eps';
  let payload = null;
  let chart = null;
  let resizeObserver = null;
  let controller = null;
  let requestSeq = 0;

  const css = `
    .cons-section{display:none;margin:16px 20px 24px;background:#fff;border:1px solid #eaedf0;border-radius:18px;padding:20px;box-shadow:0 2px 12px rgba(0,0,0,.035)}
    .cons-head{margin-bottom:12px}.cons-title{font-size:20px;font-weight:800;color:#191f28;margin:0 0 5px}.cons-desc{font-size:13px;color:#6b7684;line-height:1.55;margin:0}
    .cons-stock-tabs,.cons-period-tabs,.cons-mode-tabs{display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}.cons-stock-tabs::-webkit-scrollbar,.cons-period-tabs::-webkit-scrollbar,.cons-mode-tabs::-webkit-scrollbar{display:none}
    .cons-stock-tabs{margin:14px 0 10px}.cons-period-tabs{margin-bottom:10px}.cons-mode-tabs{margin-bottom:14px}
    .cons-btn{border:1px solid #e5e8eb;background:#fff;color:#4e5968;border-radius:999px;padding:9px 12px;font-size:13px;font-weight:700;white-space:nowrap;cursor:pointer}.cons-btn.active{background:#191f28;color:#fff;border-color:#191f28}
    .cons-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:14px}.cons-card{background:#f7f8fa;border-radius:13px;padding:12px;min-width:0}.cons-card span{display:block;color:#8b95a1;font-size:11px;margin-bottom:5px}.cons-card strong{display:block;color:#191f28;font-size:17px;line-height:1.25;overflow-wrap:anywhere}.cons-card small{display:block;color:#6b7684;font-size:10px;margin-top:4px;line-height:1.35}
    .cons-chart-wrap{position:relative;border:1px solid #edf0f2;border-radius:14px;overflow:hidden;background:#fff}.cons-chart{height:310px;width:100%}.cons-loading{height:310px;display:flex;align-items:center;justify-content:center;color:#8b95a1;font-size:13px}.cons-empty{height:240px;display:flex;align-items:center;justify-content:center;text-align:center;padding:18px;color:#8b95a1;font-size:13px;line-height:1.6}
    .cons-range{padding:22px 18px}.cons-range-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-end;margin-bottom:14px}.cons-range-head strong{font-size:20px;color:#191f28}.cons-range-head span{font-size:12px;color:#8b95a1}.cons-range-track{height:10px;background:#e5e8eb;border-radius:999px;position:relative;margin:20px 2px 8px}.cons-range-fill{position:absolute;inset:0;border-radius:999px;background:#dbeafe}.cons-range-dot{position:absolute;top:50%;width:16px;height:16px;border-radius:50%;background:#3182f6;transform:translate(-50%,-50%);box-shadow:0 0 0 4px rgba(49,130,246,.12)}.cons-range-labels{display:flex;justify-content:space-between;color:#6b7684;font-size:11px;gap:8px}.cons-foot{margin-top:10px;color:#8b95a1;font-size:11px;line-height:1.5}.cons-note{margin-top:10px;padding:10px 12px;border-radius:12px;background:#f7f8fa;color:#4e5968;font-size:12px;line-height:1.55}
    .cons-positive{color:#00a86b!important}.cons-negative{color:#f04452!important}
    @media(max-width:720px){.cons-section{margin:10px 8px 18px;padding:14px;border-radius:16px}.cons-title{font-size:18px}.cons-cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.cons-card{padding:10px}.cons-card strong{font-size:16px}.cons-chart{height:285px}.cons-loading{height:285px}.cons-btn{min-height:40px;padding:9px 13px}.cons-range{padding:18px 12px}.cons-range-head strong{font-size:18px}}
  `;

  const esc = (v) => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
  const num = (v) => Number.isFinite(Number(v)) ? Number(v) : null;
  const fmt = (v, d=2) => num(v) === null ? '-' : Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
  const tickers = () => (typeof perTickers !== 'undefined' && Array.isArray(perTickers)) ? [...perTickers] : [];
  const nameOf = (t) => { try { return (typeof perTickerNameMap !== 'undefined' && perTickerNameMap[t]) || t; } catch { return t; } };
  const periodLabel = { '0q':'이번 분기', '+1q':'다음 분기', '0y':'올해', '+1y':'내년' };

  function injectStyles(){
    if(document.getElementById('consensus-v2-style')) return;
    const style=document.createElement('style'); style.id='consensus-v2-style'; style.textContent=css; document.head.appendChild(style);
  }

  function fmtEps(v){
    const n=num(v); if(n===null)return '-';
    const kr=payload?.currency==='KRW'||ticker?.includes('.KS')||ticker?.includes('.KQ');
    return kr ? `₩${Math.round(n).toLocaleString()}` : `$${n.toLocaleString(undefined,{maximumFractionDigits:2})}`;
  }
  function fmtRevenue(v){
    const n=num(v); if(n===null)return '-';
    const kr=payload?.currency==='KRW'||ticker?.includes('.KS')||ticker?.includes('.KQ');
    if(kr){
      if(Math.abs(n)>=1e12)return `₩${(n/1e12).toFixed(1)}조`;
      if(Math.abs(n)>=1e8)return `₩${(n/1e8).toFixed(0)}억`;
      return `₩${Math.round(n).toLocaleString()}`;
    }
    if(Math.abs(n)>=1e12)return `$${(n/1e12).toFixed(2)}T`;
    if(Math.abs(n)>=1e9)return `$${(n/1e9).toFixed(1)}B`;
    if(Math.abs(n)>=1e6)return `$${(n/1e6).toFixed(1)}M`;
    return `$${n.toLocaleString(undefined,{maximumFractionDigits:0})}`;
  }
  function pct(v){const n=num(v);return n===null?'-':`${(n*100).toFixed(1)}%`;}
  function changePct(current, old){const c=num(current),o=num(old);return c===null||o===null||o===0?null:(c-o)/Math.abs(o)*100;}
  function dateShift(iso,days){const d=new Date(iso||Date.now());d.setUTCDate(d.getUTCDate()-days);return d.toISOString().slice(0,10);}

  function install(){
    injectStyles();
    const chips=document.querySelector('.metric-chips');
    const perSection=document.querySelector('#fwdper-tab .per-section');
    if(!chips||!perSection||document.querySelector('[data-metric="consensus"]'))return;

    const chip=document.createElement('button'); chip.className='metric-chip'; chip.dataset.metric='consensus'; chip.textContent='🧭 실적 컨센서스';
    const bandChip=chips.querySelector('[data-metric="bands"]');
    if(bandChip)bandChip.insertAdjacentElement('afterend',chip);else chips.appendChild(chip);

    const section=document.createElement('section'); section.id='consensus-v2-section'; section.className='cons-section';
    section.innerHTML=`
      <div class="cons-head"><h2 class="cons-title">EPS · 매출 컨센서스 추세</h2><p class="cons-desc">애널리스트 예상치가 실제로 상향·하향되는지 봅니다. EPS는 Yahoo가 제공하는 90일 추세를 사용하고, 매출은 일별 스냅샷을 직접 축적합니다.</p></div>
      <div id="cons-stock-tabs" class="cons-stock-tabs"></div>
      <div id="cons-period-tabs" class="cons-period-tabs">${Object.entries(periodLabel).map(([k,v])=>`<button class="cons-btn ${k===period?'active':''}" data-cons-period="${k}">${v}</button>`).join('')}</div>
      <div class="cons-mode-tabs"><button class="cons-btn active" data-cons-mode="eps">EPS 추세</button><button class="cons-btn" data-cons-mode="revenue">매출 추세</button></div>
      <div id="cons-cards" class="cons-cards"></div>
      <div class="cons-chart-wrap"><div id="cons-chart" class="cons-chart"></div><div id="cons-loading" class="cons-loading" style="display:none">컨센서스를 불러오는 중...</div></div>
      <div id="cons-foot" class="cons-foot"></div>
      <div id="cons-note" class="cons-note"></div>`;
    const bandSection=document.getElementById('valuation-band-section');
    if(bandSection)bandSection.insertAdjacentElement('afterend',section); else perSection.insertAdjacentElement('afterend',section);

    chip.addEventListener('click',(e)=>{e.preventDefault();activate();});
    chips.querySelectorAll('.metric-chip:not([data-metric="consensus"])').forEach(btn=>btn.addEventListener('click',()=>deactivate()));
    section.querySelectorAll('[data-cons-period]').forEach(btn=>btn.addEventListener('click',()=>{
      period=btn.dataset.consPeriod; section.querySelectorAll('[data-cons-period]').forEach(b=>b.classList.toggle('active',b===btn)); render();
    }));
    section.querySelectorAll('[data-cons-mode]').forEach(btn=>btn.addEventListener('click',()=>{
      mode=btn.dataset.consMode; section.querySelectorAll('[data-cons-mode]').forEach(b=>b.classList.toggle('active',b===btn)); render();
    }));

    const tags=document.getElementById('ticker-tags');
    if(tags){let timer=null;new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>{renderTickerTabs();if(section.style.display!=='none')ensureTickerAndLoad();},100);}).observe(tags,{childList:true,subtree:true});}
  }

  function activate(){
    document.querySelectorAll('.metric-chip').forEach(b=>b.classList.toggle('active',b.dataset.metric==='consensus'));
    const per=document.querySelector('#fwdper-tab .per-section'); if(per)per.style.display='none';
    const band=document.getElementById('valuation-band-section'); if(band)band.style.display='none';
    const section=document.getElementById('consensus-v2-section'); if(section)section.style.display='block';
    renderTickerTabs(); ensureTickerAndLoad();
  }
  function deactivate(){
    const section=document.getElementById('consensus-v2-section'); if(section)section.style.display='none';
  }

  function renderTickerTabs(){
    const el=document.getElementById('cons-stock-tabs'); if(!el)return;
    const list=tickers();
    if(!list.length){el.innerHTML='';ticker=null;return;}
    if(!ticker||!list.includes(ticker))ticker=list[0];
    el.innerHTML=list.map(t=>`<button class="cons-btn ${t===ticker?'active':''}" data-cons-ticker="${esc(t)}">${esc(nameOf(t))}</button>`).join('');
    el.querySelectorAll('[data-cons-ticker]').forEach(btn=>btn.addEventListener('click',()=>{ticker=btn.dataset.consTicker;renderTickerTabs();load();}));
  }

  function ensureTickerAndLoad(){
    const list=tickers();
    if(!list.length){ticker=null;payload=null;destroyChart();document.getElementById('cons-cards').innerHTML='';document.getElementById('cons-chart').innerHTML='<div class="cons-empty">상단에서 종목을 먼저 선택해 주세요.</div>';return;}
    if(!ticker||!list.includes(ticker))ticker=list[0]; load();
  }

  async function load(){
    if(!ticker)return;
    const seq=++requestSeq; if(controller)controller.abort(); controller=new AbortController();
    const loading=document.getElementById('cons-loading'), chartEl=document.getElementById('cons-chart');
    if(loading)loading.style.display='flex'; if(chartEl)chartEl.style.visibility='hidden';
    try{
      const r=await fetch(`/api/consensus?ticker=${encodeURIComponent(ticker)}`,{cache:'no-store',signal:controller.signal});
      if(!r.ok){let msg='';try{msg=(await r.json()).error||'';}catch{}throw new Error(msg||`HTTP ${r.status}`);}
      const data=await r.json(); if(seq!==requestSeq)return; payload=data; render();
    }catch(e){
      if(e?.name==='AbortError')return; console.error('consensus error',e); payload=null; destroyChart();
      if(chartEl){chartEl.style.visibility='visible';chartEl.innerHTML=`<div class="cons-empty">${esc(e.message||'컨센서스 데이터를 불러오지 못했습니다.')}</div>`;}
      document.getElementById('cons-cards').innerHTML='';
    }finally{if(seq===requestSeq){if(loading)loading.style.display='none';if(chartEl)chartEl.style.visibility='visible';}}
  }

  function destroyChart(){if(resizeObserver){resizeObserver.disconnect();resizeObserver=null;}if(chart){try{chart.remove();}catch{}chart=null;}}

  function render(){
    if(!payload)return;
    const row=(payload.periods||{})[period]; const cards=document.getElementById('cons-cards'), foot=document.getElementById('cons-foot'), note=document.getElementById('cons-note');
    if(!row){destroyChart();cards.innerHTML='';document.getElementById('cons-chart').innerHTML='<div class="cons-empty">이 기간의 컨센서스 데이터가 없습니다.</div>';return;}
    const e=row.earnings||{}, r=row.revenue||{}, tr=row.epsTrend||{}, rev=row.revisions||{};
    if(mode==='eps'){
      const delta=changePct(tr.current,tr['90daysAgo']??tr['30daysAgo']); const cls=delta===null?'':(delta>0?'cons-positive':delta<0?'cons-negative':'');
      cards.innerHTML=`
        <div class="cons-card"><span>EPS 컨센서스</span><strong>${fmtEps(e.avg)}</strong><small>${periodLabel[period]} · ${esc(row.endDate||'')}</small></div>
        <div class="cons-card"><span>90일 변화</span><strong class="${cls}">${delta===null?'-':`${delta>=0?'+':''}${delta.toFixed(1)}%`}</strong><small>현재 vs 90일 전 추정치</small></div>
        <div class="cons-card"><span>30일 리비전</span><strong>↑ ${fmt(rev.up30,0)} / ↓ ${fmt(rev.down30,0)}</strong><small>상향 / 하향 애널리스트 수</small></div>
        <div class="cons-card"><span>예상 범위</span><strong>${fmtEps(e.low)} ~ ${fmtEps(e.high)}</strong><small>애널리스트 ${fmt(e.analysts,0)}명</small></div>`;
      drawEps(tr);
      note.textContent='EPS 추세는 Yahoo earningsTrend가 제공하는 실제 현재·7·30·60·90일 전 애널리스트 평균 추정치입니다. 값이 없는 구간은 표시하지 않습니다.';
    }else{
      cards.innerHTML=`
        <div class="cons-card"><span>매출 컨센서스</span><strong>${fmtRevenue(r.avg)}</strong><small>${periodLabel[period]} · ${esc(row.endDate||'')}</small></div>
        <div class="cons-card"><span>예상 범위</span><strong>${fmtRevenue(r.low)} ~ ${fmtRevenue(r.high)}</strong><small>최저~최고 추정치</small></div>
        <div class="cons-card"><span>예상 성장률</span><strong class="${num(r.growth)>0?'cons-positive':num(r.growth)<0?'cons-negative':''}">${pct(r.growth)}</strong><small>Yahoo 기준 전년 대비</small></div>
        <div class="cons-card"><span>참여 애널리스트</span><strong>${fmt(r.analysts,0)}명</strong><small>현재 매출 컨센서스</small></div>`;
      drawRevenue(row,r);
      const hist=((payload.history||{})[period]||[]).filter(x=>num(x.revenue)!==null);
      note.textContent=hist.length>1 ? `매출 컨센서스는 일별 실제 스냅샷을 축적해 변화선을 표시합니다. 현재 ${hist.length}개 관측치가 있습니다.` : 'Yahoo는 과거 매출 컨센서스를 소급 제공하지 않아 임의 보간하지 않습니다. 오늘부터 일별 스냅샷을 축적하며, 초기에는 현재 평균·최저·최고 범위만 표시합니다.';
    }
    const stamp=payload.asOf||''; if(foot)foot.textContent=`데이터: ${payload.source||'Yahoo Finance'} · 기준 ${stamp ? new Date(stamp).toLocaleString() : '-'} · 기간 ${periodLabel[period]}`;
  }

  function baseChart(el){
    destroyChart(); el.innerHTML='';
    chart=LightweightCharts.createChart(el,{width:el.clientWidth,height:el.clientHeight||310,layout:{background:{type:LightweightCharts.ColorType.Solid,color:'#fff'},textColor:'#6b7684'},grid:{vertLines:{color:'#f2f4f6'},horzLines:{color:'#f2f4f6'}},rightPriceScale:{borderVisible:false},timeScale:{borderVisible:false,timeVisible:false},crosshair:{mode:LightweightCharts.CrosshairMode.Normal}});
    resizeObserver=new ResizeObserver(()=>{if(chart&&el.clientWidth>0)chart.applyOptions({width:el.clientWidth,height:el.clientHeight||310});});resizeObserver.observe(el); return chart;
  }

  function drawEps(tr){
    const el=document.getElementById('cons-chart'); if(!el||!window.LightweightCharts)return;
    const asOf=payload.asOf||new Date().toISOString();
    const specs=[[90,'90daysAgo'],[60,'60daysAgo'],[30,'30daysAgo'],[7,'7daysAgo'],[0,'current']];
    const points=specs.map(([days,key])=>({time:dateShift(asOf,days),value:num(tr[key])})).filter(x=>x.value!==null);
    if(points.length<2){destroyChart();el.innerHTML='<div class="cons-empty">EPS 추세 관측치가 충분하지 않습니다.</div>';return;}
    const c=baseChart(el); const series=c.addLineSeries({color:'#3182f6',lineWidth:3,priceLineVisible:false,lastValueVisible:true});series.setData(points);c.timeScale().fitContent();
  }

  function drawRevenue(row,r){
    const el=document.getElementById('cons-chart'); if(!el)return;
    const hist=((payload.history||{})[period]||[]).filter(x=>x.date&&num(x.revenue)!==null);
    if(hist.length>=2&&window.LightweightCharts){
      const c=baseChart(el);const series=c.addLineSeries({color:'#00a86b',lineWidth:3,priceLineVisible:false,lastValueVisible:true});series.setData(hist.map(x=>({time:x.date,value:Number(x.revenue)})));c.timeScale().fitContent();return;
    }
    destroyChart();
    const low=num(r.low),high=num(r.high),avg=num(r.avg);
    if(low===null||high===null||avg===null||high<=low){el.innerHTML='<div class="cons-empty">매출 컨센서스 범위 데이터가 충분하지 않습니다.</div>';return;}
    const pos=Math.max(0,Math.min(100,(avg-low)/(high-low)*100));
    el.innerHTML=`<div class="cons-range"><div class="cons-range-head"><div><span>현재 평균 컨센서스</span><br><strong>${fmtRevenue(avg)}</strong></div><span>${esc(row.endDate||'')}</span></div><div class="cons-range-track"><div class="cons-range-fill"></div><div class="cons-range-dot" style="left:${pos}%"></div></div><div class="cons-range-labels"><span>Low ${fmtRevenue(low)}</span><span>Avg ${fmtRevenue(avg)}</span><span>High ${fmtRevenue(high)}</span></div></div>`;
  }

  document.addEventListener('DOMContentLoaded',install);
})();
