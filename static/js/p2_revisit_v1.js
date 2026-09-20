(() => {
  'use strict';
  if (window.__chartViewP2V1) return;
  window.__chartViewP2V1 = true;

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const NAMES_KEY = 'chartview-ticker-names-v1';
  const SCREENER_KEY = 'chartview-screener-saved-v1';
  const SCREEN_KEY = 'chartview-screen-return-v1';

  const read = (key, fallback) => { try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch (_) { return fallback; } };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch (_) { return false; } };
  const toast = (message) => {
    let node = document.getElementById('p2-toast');
    if (!node) { node = document.createElement('div'); node.id = 'p2-toast'; node.className = 'p2-toast'; node.setAttribute('role','status'); document.body.appendChild(node); }
    node.textContent = message; node.classList.add('show'); clearTimeout(toast.timer); toast.timer=setTimeout(()=>node.classList.remove('show'),1800);
  };

  function installWatchlistBackup() {
    const toolbar = document.querySelector('.watchlist-v33-toolbar');
    if (!toolbar || toolbar.querySelector('[data-p2-backup]')) return;
    const group = document.createElement('div'); group.className='p2-backup-actions';
    group.innerHTML='<button type="button" data-p2-backup>백업</button><button type="button" data-p2-restore>복원</button><input type="file" accept="application/json,.json" data-p2-restore-file hidden>';
    toolbar.appendChild(group);
    group.querySelector('[data-p2-backup]').addEventListener('click', () => {
      const payload={schema:'chartview-watchlist',version:1,exportedAt:new Date().toISOString(),watchlist:read(WATCHLIST_KEY,[]),names:read(NAMES_KEY,{})};
      const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='chartview-watchlist.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000); toast('관심종목 백업 파일을 만들었어요.');
    });
    const input=group.querySelector('[data-p2-restore-file]');
    group.querySelector('[data-p2-restore]').addEventListener('click',()=>input.click());
    input.addEventListener('change',async()=>{
      const file=input.files?.[0]; if(!file)return;
      try {
        const data=JSON.parse(await file.text());
        if(data?.schema!=='chartview-watchlist'||!Array.isArray(data.watchlist)) throw new Error('invalid');
        const clean=data.watchlist.map(x=>({symbol:String(x?.symbol||x?.ticker||'').trim().toUpperCase(),name:String(x?.name||x?.symbol||'').trim()})).filter(x=>x.symbol).slice(0,20);
        write(WATCHLIST_KEY,clean); if(data.names&&typeof data.names==='object')write(NAMES_KEY,data.names);
        toast(`${clean.length}개 관심종목을 복원했어요.`); setTimeout(()=>location.reload(),500);
      } catch(_){ toast('Chart View 관심종목 백업 파일이 아니에요.'); }
      input.value='';
    });
  }

  function installScreenerSave() {
    const host=document.querySelector('.screener-custom-grid')?.parentElement;
    if(!host||host.querySelector('[data-p2-screen-save]'))return;
    const bar=document.createElement('div'); bar.className='p2-screen-save'; bar.innerHTML='<button type="button" data-p2-screen-save>조건 저장</button><button type="button" data-p2-screen-load>저장 조건 불러오기</button>';
    host.appendChild(bar);
    const collect=()=>Object.fromEntries([...document.querySelectorAll('[data-screen-custom]')].map(el=>[el.dataset.screenCustom,el.value]));
    bar.querySelector('[data-p2-screen-save]').addEventListener('click',()=>{write(SCREENER_KEY,{values:collect(),savedAt:Date.now()});toast('스크리너 조건을 저장했어요.');});
    bar.querySelector('[data-p2-screen-load]').addEventListener('click',()=>{
      const saved=read(SCREENER_KEY,null); if(!saved?.values){toast('저장된 조건이 없어요.');return;}
      Object.entries(saved.values).forEach(([key,value])=>{const el=document.querySelector(`[data-screen-custom="${CSS.escape(key)}"]`);if(el){el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));}});
      toast('저장한 조건을 불러왔어요.');
    });
  }

  function installReturnPosition() {
    document.addEventListener('click',(event)=>{
      const tab=document.querySelector('.tab-content.active')?.id;
      if(tab!=='screener-tab')return;
      const card=event.target.closest('[data-screen-card], .screener-card, [data-symbol], [data-ticker]');
      if(card)write(SCREEN_KEY,{scrollY:window.scrollY,at:Date.now()});
    },true);
    document.addEventListener('tabChanged',(event)=>{
      if(event.detail?.tab!=='screener')return;
      const saved=read(SCREEN_KEY,null); if(saved&&Date.now()-saved.at<30*60*1000)requestAnimationFrame(()=>window.scrollTo({top:Number(saved.scrollY)||0,behavior:'auto'}));
    });
  }

  function normalizeNewsTitle(value){return String(value||'').toLowerCase().replace(/\b(inc|corp|ltd|plc|co)\b/g,'').replace(/[^a-z0-9가-힣 ]/g,' ').replace(/\s+/g,' ').trim();}
  function newsKey(card){
    const title=normalizeNewsTitle(card.querySelector('.news-title,[data-news-title],h3,h4,strong')?.textContent);
    const words=title.split(' ').filter(w=>w.length>2).slice(0,7);
    return words.slice(0,4).join('|');
  }
  function groupNews() {
    document.querySelectorAll('.personalized-news-list,.home-news-list,[data-news-list]').forEach(list=>{
      const cards=[...list.children].filter(x=>x.nodeType===1); const seen=new Map();
      cards.forEach(card=>{const key=newsKey(card);if(!key)return; if(seen.has(key)){card.classList.add('p2-similar-news');card.dataset.similarTo=key;}else seen.set(key,card);});
      seen.forEach((first,key)=>{const dup=cards.filter(c=>c!==first&&c.dataset.similarTo===key);if(!dup.length)return;let badge=first.querySelector('[data-p2-similar]');if(!badge){badge=document.createElement('span');badge.dataset.p2Similar='1';badge.className='p2-similar-badge';first.appendChild(badge);}badge.textContent=`유사 뉴스 ${dup.length}건 묶음`;dup.forEach(c=>c.hidden=true);badge.onclick=()=>{const open=dup.some(c=>c.hidden);dup.forEach(c=>c.hidden=!open);badge.textContent=open?'유사 뉴스 접기':`유사 뉴스 ${dup.length}건 묶음`;};});
    });
  }

  function addRelevanceReasons() {
    document.querySelectorAll('[data-news-symbols],.personalized-news-card,.home-news-card').forEach(card=>{
      if(card.querySelector('[data-p2-relevance]'))return;
      const symbols=(card.getAttribute('data-news-symbols')||card.dataset?.symbols||'').split(',').filter(Boolean);
      if(!symbols.length)return;
      const note=document.createElement('small');note.dataset.p2Relevance='1';note.className='p2-relevance';note.textContent=`관심종목 ${symbols.slice(0,3).join(' · ')} 관련`;card.appendChild(note);
    });
  }

  function installDataStateDetails() {
    document.querySelectorAll('[data-stale="true"],[data-v413-freshness],.data-state,.freshness').forEach(node=>{
      if(node.dataset.p2StateReady)return; node.dataset.p2StateReady='1';node.tabIndex=0;node.setAttribute('role','button');node.setAttribute('aria-label',(node.textContent||'데이터 상태')+' 상세 설명');
      const show=()=>{const text=(node.textContent||'').trim();const reason=/이전|지연|stale/i.test(text)?'최신 데이터 갱신이 완료되지 않아 마지막 정상 데이터를 표시하고 있습니다.':/휴장|closed/i.test(text)?'현재 시장이 휴장 상태라 마지막 거래일 데이터를 표시합니다.':/없|미확인|missing/i.test(text)?'제공처에서 값을 확인하지 못해 해당 항목을 표시하지 않습니다.':'표시된 기준일과 조회 시각을 함께 확인해 주세요.';toast(reason);};
      node.addEventListener('click',show);node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show();}});
    });
  }

  function enhance(){installWatchlistBackup();installScreenerSave();groupNews();addRelevanceReasons();installDataStateDetails();}
  installReturnPosition();
  new MutationObserver(()=>requestAnimationFrame(enhance)).observe(document.body,{childList:true,subtree:true});
  document.addEventListener('chartview:v41-news-rendered',enhance);document.addEventListener('chartview:v37-news-rendered',enhance);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',enhance,{once:true});else enhance();
})();
