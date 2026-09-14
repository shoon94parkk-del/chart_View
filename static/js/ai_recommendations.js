(() => {
  const fmt = (v) => {
    const n = Number(v);
    return Number.isFinite(n) ? n.toLocaleString('ko-KR') : '-';
  };
  const pct = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return '-';
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  };
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  async function load() {
    const host = document.querySelector('[data-ai-recommendations]');
    if (!host) return;
    try {
      const r = await fetch('/static/data/ai_recommendations.json', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const rows = Array.isArray(data.recommendations) ? data.recommendations : [];
      if (!rows.length) {
        host.innerHTML = '<div class="ai-rec-empty">아직 누적된 추천 이력이 없습니다.</div>';
        return;
      }
      const active = rows.filter(r => (r.status || 'active') !== 'closed');
      const closed = rows.filter(r => (r.status || 'active') === 'closed');
      const ordered = [...active, ...closed].sort((a,b) => String(b.recommendedDate || '').localeCompare(String(a.recommendedDate || '')));
      host.innerHTML = ordered.map((r) => {
        const ret = Number(r.returnPct);
        const cls = Number.isFinite(ret) ? (ret > 0 ? 'up' : ret < 0 ? 'down' : '') : '';
        return `
          <article class="ai-rec-card">
            <div class="ai-rec-top">
              <div>
                <strong>${esc(r.name || r.symbol)}</strong>
                <span>${esc(r.symbol || '')}</span>
              </div>
              <em class="${cls}">${pct(r.returnPct)}</em>
            </div>
            <div class="ai-rec-grid">
              <div><span>추천일</span><b>${esc(r.recommendedDate || '-')}</b></div>
              <div><span>추천가</span><b>${fmt(r.recommendedPrice)}</b></div>
              <div><span>현재가</span><b>${fmt(r.currentPrice)}</b></div>
              <div><span>최고수익률</span><b>${pct(r.bestReturnPct)}</b></div>
            </div>
            <div class="ai-rec-bottom">
              <span class="status">${esc(r.statusLabel || ((r.status || 'active') === 'closed' ? '종료' : '관찰중'))}</span>
              <p>${esc(r.reason || '')}</p>
            </div>
          </article>`;
      }).join('');
    } catch (e) {
      host.innerHTML = '<div class="ai-rec-empty">추천 이력을 불러오지 못했습니다.</div>';
      console.error('[AI recommendations]', e);
    }
  }
  document.addEventListener('DOMContentLoaded', load);
})();
