(() => {
  'use strict';
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = (n) => Number.isFinite(+n) ? Math.round(+n).toLocaleString('ko-KR') : '-';
  const pct = (n) => Number.isFinite(+n) ? `${+n > 0 ? '+' : ''}${(+n).toFixed(2)}%` : '-';
  let cachedDay = null;
  let fetching = null;

  function installAiLedgerAssets() {
    if (!document.getElementById('ai-pick-ledger-v52-style')) {
      const link = document.createElement('link'); link.id='ai-pick-ledger-v52-style'; link.rel='stylesheet'; link.href='/static/css/ai_pick_ledger_v52.css?v=20260917v58'; document.head.appendChild(link);
    }
    if (!document.getElementById('ai-pick-ledger-v52-script')) {
      const script=document.createElement('script'); script.id='ai-pick-ledger-v52-script'; script.src='/static/js/ai_pick_ledger_v52.js?v=20260917v58'; script.async=false; document.body.appendChild(script);
    }
  }

  function addStyle(){
    if(document.getElementById('ai-daily-widget-style'))return;
    const style=document.createElement('style');
    style.id='ai-daily-widget-style';
    style.textContent=`#home-tab .ai-daily-section{margin:0 0 16px;padding:16px;background:#fff;border:1px solid #dce9fb;border-radius:20px}#home-tab .ai-daily-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:11px}#home-tab .ai-daily-head h2{margin:0;font-size:20px;color:#191f28}#home-tab .ai-daily-head p{margin:4px 0 0;font-size:12px;color:#8b95a1}#home-tab .ai-daily-more{border:0;background:transparent;color:#3182f6;font-size:12px;font-weight:800;white-space:nowrap;cursor:pointer;text-decoration:none}#home-tab .ai-daily-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}#home-tab .ai-daily-card{background:#fff;border:1px solid #edf1f5;border-radius:15px;overflow:hidden}#home-tab .ai-daily-card summary{list-style:none;cursor:pointer;padding:11px 12px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;grid-template-areas:"rank name score" "price price arrow";align-items:center;gap:5px 8px}#home-tab .ai-daily-rank{grid-area:rank;font-size:11px;font-weight:900;color:#6b7684}#home-tab .ai-daily-name{grid-area:name;min-width:0;font-size:15px;font-weight:800;color:#191f28;overflow-wrap:anywhere}#home-tab .ai-daily-score{grid-area:score;justify-self:end;display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;background:#eef6ff;color:#1b64da;font-size:11px;font-weight:800;line-height:1.2;white-space:nowrap}#home-tab .ai-daily-price{grid-area:price;min-width:0;font-size:12px;color:#4e5968;overflow-wrap:anywhere}#home-tab .ai-daily-arrow{grid-area:arrow;justify-self:end;color:#8b95a1;font-size:11px;transition:transform .15s ease}#home-tab .ai-daily-card[open] .ai-daily-arrow{transform:rotate(180deg)}#home-tab .ai-daily-price .up{color:#f04452}#home-tab .ai-daily-price .down{color:#3182f6}#home-tab .ai-daily-detail{padding:10px 12px;border-top:1px solid #f3f5f7}#home-tab .ai-daily-reason{margin:0;color:#6b7684;font-size:12px;line-height:1.55}#home-tab .ai-daily-badge{display:inline-block;margin-top:8px;padding:5px 8px;border-radius:999px;background:#eef6ff;color:#1b64da;font-size:10px;font-weight:800}@media(max-width:700px){#home-tab .ai-daily-grid{grid-template-columns:1fr}#home-tab .ai-daily-section{padding:13px}#home-tab .ai-daily-card summary{grid-template-columns:auto minmax(0,1fr) auto;grid-template-areas:"rank name score" "price price arrow"}#home-tab .ai-daily-name{white-space:normal}#home-tab .ai-daily-score{white-space:nowrap}}`;
    document.head.appendChild(style);
  }

  function cardMarkup(day){
    const rows=Array.isArray(day?.top3)?day.top3.slice(0,3):[];
    if(!rows.length)return'';
    const cards=rows.map(x=>{
      const c=Number(x.changePct)>0?'up':Number(x.changePct)<0?'down':'';
      const score=Number(x.totalScore)>0?`${esc(x.totalScore)}점`:'사용자 PICK';
      const name=esc(x.name||x.symbol);
      return `<details class="ai-daily-card"><summary aria-label="${name} 추천 사유 보기"><span class="ai-daily-rank">PICK</span><span class="ai-daily-name">${name}</span><span class="ai-daily-score">${score}</span><span class="ai-daily-price">${money(x.close)}원 · <span class="${c}">${pct(x.changePct)}</span></span><span class="ai-daily-arrow" aria-hidden="true">⌄</span></summary><div class="ai-daily-detail"><p class="ai-daily-reason">${esc(x.reason||'')}</p><span class="ai-daily-badge">${esc(x.grade||'관찰')}</span></div></details>`;
    }).join('');
    return `<div class="ai-daily-head"><div><h2>ChartView PICK 3</h2><p>${esc(day.tradeDate)} 종가 기준</p></div><a class="ai-daily-more" href="/?tab=screener&view=ai-picks">전체 기록 →</a></div><div class="ai-daily-grid">${cards}</div>`;
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

  async function loadDay(){
    if(cachedDay)return cachedDay;
    if(fetching)return fetching;
    fetching=(async()=>{
      const m=await fetch(`/static/data/ai_daily_rankings_meta.json?t=${Date.now()}`,{cache:'no-store'});
      const meta=m.ok?await m.json():{};
      const r=await fetch(`/static/data/ai_daily_rankings.json?v=${encodeURIComponent(meta.updated||Date.now())}`,{cache: 'default'});
      if(!r.ok)throw new Error(`HTTP ${r.status}`);
      const data=await r.json();
      cachedDay=[...(data.days||[])].sort((a,b)=>String(b.tradeDate||'').localeCompare(String(a.tradeDate||'')))[0]||null;
      return cachedDay;
    })().finally(()=>fetching=null);
    return fetching;
  }

  async function mount(attempt=0){
    const s=placeSection();
    if(!s){if(attempt<80)setTimeout(()=>mount(attempt+1),100);return;}
    addStyle();
    try{const d=await loadDay();s.innerHTML=cardMarkup(d);}
    catch(e){s.innerHTML='<span style="color:#8b95a1;font-size:13px">PICK 데이터를 불러오지 못했습니다.</span>';}
  }

  document.addEventListener('click',(event)=>{
    const link=event.target.closest('#ai-daily-section .ai-daily-more');
    if(!link)return;
    if(typeof window.__openAiPickLedger==='function'){
      event.preventDefault();
      window.__openAiPickLedger();
    }
  });

  installAiLedgerAssets();
  addStyle();
  mount();
  document.addEventListener('DOMContentLoaded',()=>mount());
  window.addEventListener('pageshow',()=>{cachedDay=null;mount();});
})();
