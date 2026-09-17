(() => {
  'use strict';

  if (window.__chartViewPickPerformanceV56Installed) return;
  window.__chartViewPickPerformanceV56Installed = true;

  const HOME_VISIBLE = 4;
  const REC_URL = '/static/data/ai_recommendations.json';
  let records = [];
  let refreshing = false;

  const n = (value) => {
    const x = Number(value);
    return Number.isFinite(x) ? x : null;
  };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function formatPrice(symbol, value) {
    const price = n(value);
    if (price === null) return '—';
    if (/\.(KS|KQ)$/.test(String(symbol || '').toUpperCase())) {
      return `${Math.round(price).toLocaleString('ko-KR')}원`;
    }
    return `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function formatReturn(value) {
    const x = n(value);
    if (x === null) return '—';
    return `${x > 0 ? '+' : ''}${x.toFixed(2)}%`;
  }

  function returnClass(value) {
    const x = n(value);
    return x === null ? '' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
  }

  function compactDate(value) {
    const match = String(value || '').match(/^\d{4}-(\d{2})-(\d{2})$/);
    return match ? `${match[1]}.${match[2]}` : String(value || '');
  }

  function keepWatchlistOneMonthSummary() {
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return false;

    const label = section.querySelector('.home-watchlist-v30-head span');
    if (label) label.textContent = 'MY STOCKS · 1달 수익률';

    const more = section.querySelector('[data-home-watch-all]');
    if (more) more.textContent = '더보기 →';

    const cards = [...section.querySelectorAll('[data-home-watch-open]')];
    cards.forEach((card, index) => {
      const hidden = index >= HOME_VISIBLE;
      card.hidden = hidden;
      card.style.display = hidden ? 'none' : '';
    });

    section.querySelectorAll('.watch-rec-baseline-v55').forEach((node) => node.remove());
    return true;
  }

  async function loadRecommendations() {
    try {
      const response = await fetch(`${REC_URL}?v=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      records = Array.isArray(payload?.recommendations) ? payload.recommendations : [];
    } catch (error) {
      console.error('[PICK v56] recommendation load failed', error);
      records = [];
    }
  }

  function currentPickDate(section) {
    const text = section?.querySelector('.ai-daily-head p')?.textContent || '';
    return text.match(/(20\d{2}-\d{2}-\d{2})/)?.[1] || '';
  }

  function findRecommendation(day, name) {
    const normalized = String(name || '').trim();
    return records.find((row) => String(row?.recommendedDate || '') === day && String(row?.name || '').trim() === normalized)
      || records.find((row) => String(row?.name || '').trim() === normalized);
  }

  async function fetchCurrentPrices(symbols) {
    const unique = [...new Set(symbols.filter(Boolean))].slice(0, 6);
    if (!unique.length) return new Map();
    const query = new URLSearchParams({ tickers: unique.join(','), period: '1mo' });
    try {
      const response = await fetch(`/api/compare?${query.toString()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const map = new Map();
      for (const row of Array.isArray(payload?.stocks) ? payload.stocks : []) {
        const symbol = String(row?.ticker || '').toUpperCase();
        const price = n(row?.price);
        if (symbol && price !== null && price > 0) map.set(symbol, price);
      }
      return map;
    } catch (error) {
      console.error('[PICK v56] current price load failed', error);
      return new Map();
    }
  }

  function ensureStyle() {
    if (document.getElementById('pick-performance-v56-style')) return;
    const style = document.createElement('style');
    style.id = 'pick-performance-v56-style';
    style.textContent = `
      #home-tab .ai-daily-card summary{
        grid-template-areas:'name score' 'price arrow' !important;
      }
      #home-tab .ai-daily-price{white-space:normal!important;line-height:1.45}
      #home-tab .ai-daily-price .pick-v56-now{font-weight:800;color:#333d4b}
      @media(max-width:700px){
        #home-tab .ai-daily-card summary{
          grid-template-columns:minmax(0,1fr) auto auto!important;
          grid-template-areas:'name score arrow' 'price score arrow'!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  async function syncPicks() {
    const section = document.getElementById('ai-daily-section');
    if (!section) return false;

    ensureStyle();
    section.querySelectorAll('.ai-daily-rank').forEach((node) => node.remove());

    const day = currentPickDate(section);
    const cards = [...section.querySelectorAll('.ai-daily-card')];
    if (!cards.length || !records.length) return Boolean(cards.length);

    const pairs = cards.map((card) => {
      const name = card.querySelector('.ai-daily-name')?.textContent?.trim() || '';
      return { card, rec: findRecommendation(day, name) };
    });
    const prices = await fetchCurrentPrices(pairs.map(({ rec }) => String(rec?.symbol || '').toUpperCase()));

    for (const { card, rec } of pairs) {
      if (!rec) continue;
      const symbol = String(rec.symbol || '').toUpperCase();
      const base = n(rec.recommendedPrice);
      const current = prices.get(symbol) ?? n(rec.currentPrice);
      if (base === null || base <= 0 || current === null || current <= 0) continue;

      const ret = (current / base - 1) * 100;
      const priceNode = card.querySelector('.ai-daily-price');
      if (!priceNode) continue;
      const cls = returnClass(ret);
      priceNode.innerHTML = `추천 ${esc(compactDate(rec.recommendedDate))} 종가 ${esc(formatPrice(symbol, base))} → 현재 <span class="pick-v56-now">${esc(formatPrice(symbol, current))}</span> · <span class="${cls}">${esc(formatReturn(ret))}</span>`;
    }
    return true;
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      keepWatchlistOneMonthSummary();
      await syncPicks();
    } finally {
      refreshing = false;
    }
  }

  async function boot(attempt = 0) {
    keepWatchlistOneMonthSummary();
    if (!records.length) await loadRecommendations();
    const ready = await syncPicks();
    if (!ready && attempt < 80) setTimeout(() => boot(attempt + 1), 125);
  }

  document.addEventListener('chartview:watchlist-change', () => setTimeout(keepWatchlistOneMonthSummary, 60));
  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(refresh, 120);
  }, true);

  setInterval(refresh, 30000);
  setInterval(async () => {
    await loadRecommendations();
    await refresh();
  }, 5 * 60 * 1000);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), { once: true });
  else boot();
})();
