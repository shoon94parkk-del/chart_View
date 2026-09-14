(() => {
  'use strict';
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = (n) => Number.isFinite(+n) ? Math.round(+n).toLocaleString('ko-KR') : '-';
  const pct = (n) => Number.isFinite(+n) ? `${+n > 0 ? '+' : ''}${(+n).toFixed(2)}%` : '-';
  let loaded = false;

  function addStyle() {
    if (document.getElementById('ai-daily-widget-style')) return;
    const style = document.createElement('style');
    style.id = 'ai-daily-widget-style';
    style.textContent = `
      #home-tab .ai-daily-section{margin:14px 0 18px;padding:18px;background:linear-gradient(145deg,#ffffff,#f8fbff);border:1px solid #dce9fb;border-radius:22px;box-shadow:0 8px 26px rgba(31,72,126,.09)}
      #home-tab .ai-daily-head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin-bottom:14px}
      #home-tab .ai-daily-head h2{margin:0;font-size:20px;color:#191f28;letter-spacing:-.3px}
      #home-tab .ai-daily-head p{margin:5px 0 0;font-size:12px;color:#8b95a1}
      #home-tab .ai-daily-more{color:#3182f6;text-decoration:none;font-size:12px;font-weight:800;white-space:nowrap}
      #home-tab .ai-daily-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
      #home-tab .ai-daily-card{background:#fff;border:1px solid #edf1f5;border-radius:16px;padding:14px;min-width:0}
      #home-tab .ai-daily-rank{font-size:12px;font-weight:900;color:#6b7684;margin-bottom:8px}
      #home-tab .ai-daily-card:nth-child(1) .ai-daily-rank{color:#c98500}
      #home-tab .ai-daily-name{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
      #home-tab .ai-daily-name strong{font-size:16px;color:#191f28;line-height:1.3}
      #home-tab .ai-daily-score{font-size:18px;font-weight:900;color:#1b64da;white-space:nowrap}
      #home-tab .ai-daily-price{margin-top:7px;font-size:13px;color:#4e5968}
      #home-tab .ai-daily-price .up{color:#f04452;font-weight:800} #home-tab .ai-daily-price .down{color:#3182f6;font-weight:800}
      #home-tab .ai-daily-reason{margin:10px 0 0;color:#6b7684;font-size:12px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
      #home-tab .ai-daily-badge{display:inline-block;margin-top:10px;padding:5px 8px;border-radius:999px;background:#eef6ff;color:#1b64da;font-size:10px;font-weight:800}
      #home-tab .ai-daily-status{margin-top:12px;padding-top:11px;border-top:1px solid #f0f2f5;color:#8b95a1;font-size:10px;line-height:1.4}
      @media(max-width:700px){#home-tab .ai-daily-section{margin:10px 0 16px;padding:14px}#home-tab .ai-daily-grid{grid-template-columns:1fr}#home-tab .ai-daily-card{padding:13px}#home-tab .ai-daily-head{align-items:center}#home-tab .ai-daily-head h2{font-size:18px}#home-tab .ai-daily-reason{-webkit-line-clamp:3}}
    `;
    document.head.appendChild(style);
  }

  async function getLatestDay() {
    const r = await fetch('/static/data/ai_daily_rankings.json', {cache:'no-store'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const days = Array.isArray(d.days) ? d.days : [];
    return [...days].sort((a,b)=>String(b.tradeDate||'').localeCompare(String(a.tradeDate||'')))[0] || null;
  }

  function cardMarkup(day) {
    const rows = Array.isArray(day?.top3) ? day.top3.slice(0,3) : [];
    if (!rows.length) return '';
    return `
      <div class="ai-daily-head"><div><h2>오늘의 AI TOP3</h2><p>${esc(day.tradeDate)} 확정 종가 기준 · 업황 70 + 기술 30</p></div><a class="ai-daily-more" href="/static/recommendations.html">전체 기록 →</a></div>
      <div class="ai-daily-grid">${rows.map(x=>{
        const cls=Number(x.changePct)>0?'up':Number(x.changePct)<0?'down':'';
        return `<article class="ai-daily-card"><div class="ai-daily-rank">${x.rank===1?'🥇':x.rank===2?'🥈':'🥉'} ${x.rank}위</div><div class="ai-daily-name"><strong>${esc(x.name||x.symbol)}</strong><span class="ai-daily-score">${esc(x.totalScore)}점</span></div><div class="ai-daily-price">${money(x.close)}원 · <span class="${cls}">${pct(x.changePct)}</span></div><p class="ai-daily-reason">${esc(x.reason||'')}</p><span class="ai-daily-badge">${esc(x.grade||'관찰')}</span></article>`;
      }).join('')}</div><div class="ai-daily-status">${esc(day.status||'')}</div>`;
  }

  async function ensure(attempt = 0) {
    const home = document.querySelector('#home-tab .home-v8');
    if (!home) {
      if (attempt < 160) setTimeout(() => ensure(attempt + 1), 50);
      return;
    }
    addStyle();
    let section = document.getElementById('ai-daily-section');
    if (!section) {
      section = document.createElement('section');
      section.id = 'ai-daily-section';
      section.className = 'ai-daily-section';
      section.innerHTML = '<div style="color:#8b95a1;font-size:13px">오늘의 추천을 불러오는 중...</div>';
      const market = document.getElementById('home-market-v9');
      if (market) market.insertAdjacentElement('afterend', section); else home.prepend(section);
      document.dispatchEvent(new CustomEvent('chartview:ai-top3-ready'));
    }
    if (loaded) return;
    try {
      const day = await getLatestDay();
      const html = cardMarkup(day);
      if (!html) { section.remove(); return; }
      section.innerHTML = html;
      loaded = true;
      document.dispatchEvent(new CustomEvent('chartview:ai-top3-ready'));
    } catch (e) {
      console.error('[AI daily widget]', e);
      section.remove();
    }
  }

  window.__ensureAiDailyTop3 = () => ensure(0);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => ensure(0), {once:true}); else ensure(0);
})();