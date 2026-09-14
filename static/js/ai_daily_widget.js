(() => {
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = (n) => Number.isFinite(+n) ? Math.round(+n).toLocaleString('ko-KR') : '-';
  const pct = (n) => Number.isFinite(+n) ? `${+n > 0 ? '+' : ''}${(+n).toFixed(2)}%` : '-';

  function addStyle() {
    if (document.getElementById('ai-daily-widget-style')) return;
    const style = document.createElement('style');
    style.id = 'ai-daily-widget-style';
    style.textContent = `
      .ai-daily-section{margin:14px 16px 18px;padding:18px;background:linear-gradient(145deg,#ffffff,#f8fbff);border:1px solid #e7edf5;border-radius:20px;box-shadow:0 5px 20px rgba(31,72,126,.07)}
      .ai-daily-head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin-bottom:14px}.ai-daily-head h2{margin:0;font-size:19px;color:#191f28}.ai-daily-head p{margin:5px 0 0;font-size:12px;color:#8b95a1}.ai-daily-more{color:#3182f6;text-decoration:none;font-size:12px;font-weight:800;white-space:nowrap}
      .ai-daily-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.ai-daily-card{background:#fff;border:1px solid #edf1f5;border-radius:16px;padding:14px;min-width:0}.ai-daily-rank{font-size:12px;font-weight:900;color:#6b7684;margin-bottom:8px}.ai-daily-card:nth-child(1) .ai-daily-rank{color:#d89500}.ai-daily-name{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.ai-daily-name strong{font-size:16px;color:#191f28;line-height:1.3}.ai-daily-score{font-size:18px;font-weight:900;color:#1b64da}.ai-daily-price{margin-top:7px;font-size:13px;color:#4e5968}.ai-daily-price .up{color:#f04452;font-weight:800}.ai-daily-price .down{color:#3182f6;font-weight:800}.ai-daily-reason{margin:10px 0 0;color:#6b7684;font-size:12px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.ai-daily-badge{display:inline-block;margin-top:10px;padding:5px 8px;border-radius:999px;background:#eef6ff;color:#1b64da;font-size:10px;font-weight:800}.ai-daily-status{margin-top:12px;padding-top:11px;border-top:1px solid #f0f2f5;color:#8b95a1;font-size:10px;line-height:1.4}
      @media(max-width:700px){.ai-daily-section{margin:10px 12px 16px;padding:14px}.ai-daily-grid{grid-template-columns:1fr}.ai-daily-card{padding:13px}.ai-daily-head{align-items:center}.ai-daily-head h2{font-size:18px}.ai-daily-reason{-webkit-line-clamp:3}}
    `;
    document.head.appendChild(style);
  }

  async function render() {
    const chartTab = document.getElementById('chart-tab');
    if (!chartTab || document.getElementById('ai-daily-section')) return;
    addStyle();
    const section = document.createElement('section');
    section.id = 'ai-daily-section';
    section.className = 'ai-daily-section';
    const anchor = chartTab.querySelector('.search-section');
    if (anchor) chartTab.insertBefore(section, anchor); else chartTab.prepend(section);
    section.innerHTML = '<div style="color:#8b95a1;font-size:13px">오늘의 추천을 불러오는 중...</div>';
    try {
      const r = await fetch('/static/data/ai_daily_rankings.json', {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const days = Array.isArray(d.days) ? d.days : [];
      if (!days.length) { section.remove(); return; }
      const day = [...days].sort((a,b)=>String(b.tradeDate||'').localeCompare(String(a.tradeDate||'')))[0];
      const rows = Array.isArray(day.top3) ? day.top3.slice(0,3) : [];
      if (!rows.length) { section.remove(); return; }
      section.innerHTML = `
        <div class="ai-daily-head"><div><h2>오늘의 AI TOP3</h2><p>${esc(day.tradeDate)} 확정 종가 기준 · 업황 70 + 기술 30</p></div><a class="ai-daily-more" href="/static/recommendations.html">추천 기록 전체 보기 →</a></div>
        <div class="ai-daily-grid">${rows.map(x=>{
          const cls=Number(x.changePct)>0?'up':Number(x.changePct)<0?'down':'';
          return `<article class="ai-daily-card"><div class="ai-daily-rank">${x.rank===1?'🥇':x.rank===2?'🥈':'🥉'} ${x.rank}위</div><div class="ai-daily-name"><strong>${esc(x.name||x.symbol)}</strong><span class="ai-daily-score">${esc(x.totalScore)}점</span></div><div class="ai-daily-price">${money(x.close)}원 · <span class="${cls}">${pct(x.changePct)}</span></div><p class="ai-daily-reason">${esc(x.reason||'')}</p><span class="ai-daily-badge">${esc(x.grade||'관찰')}</span></article>`;
        }).join('')}</div><div class="ai-daily-status">${esc(day.status||'')}</div>`;
    } catch (e) {
      console.error('[AI daily widget]', e);
      section.remove();
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render); else render();
})();
