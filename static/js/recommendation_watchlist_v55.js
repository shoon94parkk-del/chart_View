(() => {
  'use strict';

  if (window.__chartViewRecommendationWatchlistV55Installed) return;
  window.__chartViewRecommendationWatchlistV55Installed = true;

  const REC_URL = '/static/data/ai_recommendations.json';
  let latestRecommendations = [];
  let queued = false;

  const n = (value) => {
    const x = Number(value);
    return Number.isFinite(x) ? x : null;
  };

  function latestRows(rows) {
    const valid = (Array.isArray(rows) ? rows : []).filter((row) => {
      const date = String(row?.recommendedDate || '').slice(0, 10);
      const base = n(row?.recommendedPrice);
      return date && base !== null && base > 0;
    });
    const latestDate = valid.reduce((max, row) => {
      const date = String(row.recommendedDate || '').slice(0, 10);
      return date > max ? date : max;
    }, '');
    return valid
      .filter((row) => String(row.recommendedDate || '').slice(0, 10) === latestDate)
      .sort((a, b) => Number(a.rank || 99) - Number(b.rank || 99));
  }

  function recommendationReturn(rec) {
    const current = n(rec?.currentPrice);
    const base = n(rec?.recommendedPrice);
    if (current !== null && base !== null && base > 0) return (current / base - 1) * 100;
    return n(rec?.returnPct);
  }

  function formatPrice(value) {
    const x = n(value);
    return x === null ? '—' : `${Math.round(x).toLocaleString('ko-KR')}원`;
  }

  function formatReturn(value) {
    const x = n(value);
    if (x === null) return '—';
    return `${x > 0 ? '+' : ''}${x.toFixed(2)}%`;
  }

  function returnClass(value) {
    const x = n(value);
    return x === null ? '' : x > 0 ? 'up' : x < 0 ? 'down' : '';
  }

  function dateLabel(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return match ? `${match[2]}.${match[3]}` : String(value || '');
  }

  function renderPickPerformance(card, rec) {
    const node = card?.querySelector('.ai-daily-price');
    if (!node || !rec) return;

    const current = n(rec.currentPrice);
    const base = n(rec.recommendedPrice);
    const ret = recommendationReturn(rec);
    if (base === null || current === null || ret === null) return;

    const signature = `${rec.recommendedDate}|${base}|${current}|${ret.toFixed(4)}`;
    if (node.dataset.cvRecommendationSignature === signature) return;
    node.dataset.cvRecommendationSignature = signature;
    node.title = 'ChartView 추천일 종가 대비 현재가';

    const prefix = document.createTextNode(
      `추천 ${dateLabel(rec.recommendedDate)} 종가 ${formatPrice(base)} → 현재 ${formatPrice(current)} · `
    );
    const performance = document.createElement('span');
    performance.className = returnClass(ret);
    performance.textContent = formatReturn(ret);
    node.replaceChildren(prefix, performance);
  }

  function syncPicks() {
    const section = document.querySelector('#ai-daily-section');
    if (!section) return;

    section.querySelectorAll('.ai-daily-rank').forEach((rank) => rank.remove());
    const cards = [...section.querySelectorAll('.ai-daily-card')];
    cards.forEach((card, index) => renderPickPerformance(card, latestRecommendations[index]));
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      syncPicks();
    });
  }

  async function loadRecommendations() {
    try {
      const response = await fetch(`${REC_URL}?v=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      latestRecommendations = latestRows(payload?.recommendations);
      schedule();
    } catch (error) {
      console.warn('[ChartView PICK performance]', error);
    }
  }

  function boot() {
    if (typeof MutationObserver !== 'undefined' && document.body) {
      new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    }
    loadRecommendations();
    schedule();
    setInterval(loadRecommendations, 5 * 60 * 1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
