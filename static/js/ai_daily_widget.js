(() => {
  'use strict';
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const pct = (n) => Number.isFinite(+n) ? `${+n > 0 ? '+' : ''}${(+n).toFixed(2)}%` : '-';
  const tone = (n) => Number(n) > 0 ? 'up' : Number(n) < 0 ? 'down' : 'flat';
  let cachedHomeData = null;
  let fetching = null;
  const HOME_PICK_CACHE_KEY = 'chartview-home-pick-v1';

  function readPickCache(){
    try{return JSON.parse(localStorage.getItem(HOME_PICK_CACHE_KEY)||'null');}catch(_){return null;}
  }
  function writePickCache(data){
    try{localStorage.setItem(HOME_PICK_CACHE_KEY,JSON.stringify(data));}catch(_){}
  }

  function installAiLedgerAssets() {
    if (!document.getElementById('ai-pick-ledger-v52-style')) {
      const link = document.createElement('link'); link.id='ai-pick-ledger-v52-style'; link.rel='stylesheet'; link.href='/static/css/ai_pick_ledger_v52.css?v=20260917v58'; document.head.appendChild(link);
    }
    if (!document.getElementById('ai-pick-ledger-v52-script')) {
      const script=document.createElement('script'); script.id='ai-pick-ledger-v52-script'; script.src='/static/js/ai_pick_ledger_v52.js?v=20260918v59'; script.async=false; document.body.appendChild(script);
    }
  }

  function addStyle(){
    if(document.getElementById('ai-daily-widget-style'))return;
    const style=document.createElement('style');
    style.id='ai-daily-widget-style';
    style.textContent=`#home-tab .ai-daily-section{margin:0 0 16px;padding:18px;background:#fff;border:1px solid #dce9fb;border-radius:20px}#home-tab .ai-daily-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}#home-tab .ai-daily-head h2{margin:0;font-size:21px;color:#191f28;letter-spacing:-.02em}#home-tab .ai-daily-head p{margin:5px 0 0;font-size:12px;color:#8b95a1}#home-tab .ai-daily-more{border:0;background:transparent;color:#3182f6;font-size:12px;font-weight:800;white-space:nowrap;cursor:pointer;text-decoration:none;padding-top:3px}#home-tab .ai-daily-performance{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(190px,.65fr);gap:10px}#home-tab .ai-daily-performance-main{min-width:0;padding:17px 18px;border-radius:17px;background:#f7f9fc;border:1px solid #edf1f5}#home-tab .ai-daily-performance-label{display:block;font-size:12px;font-weight:800;color:#6b7684;margin-bottom:6px}#home-tab .ai-daily-performance-value{display:block;font-size:34px;line-height:1.1;font-weight:900;letter-spacing:-.04em;color:#333d4b}#home-tab .ai-daily-performance-value.up{color:#f04452}#home-tab .ai-daily-performance-value.down{color:#3182f6}#home-tab .ai-daily-performance-main small{display:block;margin-top:8px;color:#8b95a1;font-size:11px}#home-tab .ai-daily-kpis{display:grid;grid-template-columns:1fr;gap:8px}#home-tab .ai-daily-kpi{padding:12px 14px;border-radius:15px;border:1px solid #edf1f5;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:10px}#home-tab .ai-daily-kpi span{font-size:11px;color:#8b95a1;font-weight:700}#home-tab .ai-daily-kpi b{font-size:16px;color:#333d4b}#home-tab .ai-daily-today{display:flex;align-items:center;gap:9px;margin-top:12px;min-width:0}#home-tab .ai-daily-today-label{font-size:11px;font-weight:800;color:#8b95a1;white-space:nowrap}#home-tab .ai-daily-today-chips{display:flex;gap:6px;flex-wrap:wrap;min-width:0}#home-tab .ai-daily-today-chip{display:inline-flex;align-items:center;max-width:100%;padding:5px 8px;border-radius:999px;background:#eef6ff;color:#1b64da;font-size:11px;font-weight:800;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media(max-width:700px){#home-tab .ai-daily-section{padding:14px}#home-tab .ai-daily-performance{grid-template-columns:1fr}#home-tab .ai-daily-performance-main{padding:15px 16px}#home-tab .ai-daily-performance-value{font-size:31px}#home-tab .ai-daily-kpis{grid-template-columns:1fr 1fr;gap:8px}#home-tab .ai-daily-kpi{display:block;padding:10px 12px}#home-tab .ai-daily-kpi span,#home-tab .ai-daily-kpi b{display:block}#home-tab .ai-daily-kpi b{margin-top:3px;font-size:15px}#home-tab .ai-daily-today{align-items:flex-start}}`;
    document.head.appendChild(style);
  }

  function summaryMarkup(payload){
    const day=payload?.day;
    const rows=Array.isArray(payload?.recommendations)?payload.recommendations:[];
    const today=Array.isArray(day?.top3)?day.top3.slice(0,3):[];
    if(!day && !rows.length)return'';
    const tracked=rows.filter(row=>Number.isFinite(Number(row.returnPct)));
    const avgReturn=tracked.length?tracked.reduce((sum,row)=>sum+Number(row.returnPct),0)/tracked.length:null;
    const wins=tracked.filter(row=>Number(row.returnPct)>0).length;
    const winRate=tracked.length?Math.round(wins/tracked.length*100):0;
    const latestClose=tracked.reduce((max,row)=>String(row.lastUpdatedTradeDate||'')>max?String(row.lastUpdatedTradeDate||''):max,'')||day?.tradeDate||'';
    const chips=today.map(row=>`<span class="ai-daily-today-chip">${esc(row.name||row.symbol||'-')}</span>`).join('');
    return `<div class="ai-daily-head"><div><h2>ChartView PICK</h2><p>${esc(day?.tradeDate||latestClose)} 최종 선정 · 누적 성과 추적</p></div><button type="button" class="ai-daily-more" data-ai-pick-ledger>전체 기록 →</button></div><div class="ai-daily-performance"><div class="ai-daily-performance-main"><span class="ai-daily-performance-label">누적 PICK 평균 수익률</span><strong class="ai-daily-performance-value ${tone(avgReturn)}">${pct(avgReturn)}</strong><small>${esc(latestClose)} 종가 기준 · 추천 종목 동일가중 평균</small></div><div class="ai-daily-kpis"><div class="ai-daily-kpi"><span>누적 추천</span><b>${rows.length.toLocaleString('ko-KR')}건</b></div><div class="ai-daily-kpi"><span>수익 구간</span><b>${winRate}%</b></div></div></div><div class="ai-daily-today"><span class="ai-daily-today-label">오늘 PICK</span><div class="ai-daily-today-chips">${chips||'<span class="ai-daily-today-chip">선정 대기</span>'}</div></div>`;
  }

  function getHost(){
    const home=document.querySelector('#home-tab .home-v8');
    if(!home)return null;
    return{home,market:document.getElementById('home-market-v9'),watchlist:document.getElementById('home-watchlist-v30')};
  }

  function placeSection(){
    const h=getHost();
    if(!h)return null;
    let s=document.getElementById('ai-daily-section');
    if(!s){s=document.createElement('section');s.id='ai-daily-section';s.className='ai-daily-section';}
    if(h.market?.parentElement===h.home)h.market.insertAdjacentElement('afterend',s);
    else if(h.watchlist?.parentElement===h.home)h.home.insertBefore(s,h.watchlist);
    else if(s.parentElement!==h.home)h.home.prepend(s);
    return s;
  }

  async function loadHomeData(){
    if(cachedHomeData)return cachedHomeData;
    if(fetching)return fetching;
    fetching=(async()=>{
      const response=await fetch('/api/home-bootstrap',{cache:'default'});
      if(!response.ok)throw new Error(`HTTP ${response.status}: home bootstrap`);
      const data=await response.json();
      cachedHomeData={day:data?.day||null,recommendations:Array.isArray(data?.recommendations)?data.recommendations:[]};
      writePickCache(cachedHomeData);
      return cachedHomeData;
    })().finally(()=>fetching=null);
    return fetching;
  }

  async function mount(attempt=0){
    const s=placeSection();
    if(!s){if(attempt<80)setTimeout(()=>mount(attempt+1),100);return;}
    addStyle();
    const saved=readPickCache();
    if(saved&&!cachedHomeData)s.innerHTML=summaryMarkup(saved);
    try{const data=await loadHomeData();s.innerHTML=summaryMarkup(data);}
    catch(e){s.innerHTML='<span style="color:#8b95a1;font-size:13px">PICK 데이터를 불러오지 못했습니다.</span>';console.error('[ChartView PICK home]',e);}
  }

  document.addEventListener('click',(event)=>{
    const link=event.target.closest('#ai-daily-section .ai-daily-more');
    if(!link)return;
    event.preventDefault();
    if(typeof window.__openAiPickLedger==='function') window.__openAiPickLedger();
    else {
      installAiLedgerAssets();
      setTimeout(()=>window.__openAiPickLedger?.(),120);
    }
  });

  installAiLedgerAssets();
  addStyle();
  mount();
  document.addEventListener('DOMContentLoaded',()=>mount());
  window.addEventListener('pageshow',()=>{cachedHomeData=null;mount();});
})();
