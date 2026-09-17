(() => {
  'use strict';

  if (window.__chartViewPickPerformanceV56Installed) return;
  window.__chartViewPickPerformanceV56Installed = true;

  const HOME_VISIBLE = 4;
  const REC_URL = '/static/data/ai_recommendations.json';
  const REFRESH_MS = 60 * 1000;

  let latestDate = '';
  let latestPicks = [];
  let quotes = new Map();
  let loading = false;
  let queued = false;
  let observer = null;

  const n = (value) => {
    const x = Number(value);
    return Number.isFinite(x) ? x : null;
  };

  const normalize = (value) => String(value || '').replace(/\s+/g, '').toLowerCase();

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function formatPrice(symbol, value) {
    const price = n(value);
    if (price === null) return '—';
    if (/\.(KS|KQ)$/.test(symbol)) return `${Math.round(price).toLocaleString('ko-KR')}원`;
    return `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
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

  function calcReturn(currentPrice, recommendedPrice) {
    const current = n(currentPrice);
    const base = n(recommendedPrice);
    if (current === null || base === null || base <= 0) return null;
    return (current / base - 1) * 100;
  }

  function pickRows(rows) {
    const valid = (Array.isArray(rows) ? rows : []).filter((row) => {
      return row?.recommendedDate && row?.symbol && n(row?.recommendedPrice) > 0;
    });
    latestDate = valid.reduce((max, row) => String(row.recommendedDate) > max ? String(row.recommendedDate) : max, '');
    return valid
      .filter((row) => String(row.recommendedDate) === latestDate)
      .sort((a, b) => Number(a.rank || 99) - Number(b.rank || 99))
      .slice(0, 3);
  }

  async function fetchJson(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
    return response.json();
  }

  async function loadPickPerformance() {
    if (loading) return;
    loading = true;
    try {
      const data = await fetchJson(`${REC_URL}?v=${Date.now()}`);
      latestPicks = pickRows(data?.recommendations);
      const symbols = latestPicks.map((row) => String(row.symbol).toUpperCase());
      quotes = new Map();

      if (symbols.length) {
        try {
          const quoteData = await fetchJson(`/api/compare?tickers=${encodeURIComponent(symbols.join(','))}&period=1mo`);
          for (const row of Array.isArray(quoteData?.stocks) ? quoteData.stocks : []) {
            const symbol = String(row?.ticker || '').toUpperCase();
            const price = n(row?.price);
            if (symbol && price !== null && price > 0) quotes.set(symbol, price);
          }
        } catch (error) {
          console.warn('[ChartView PICK] live quote fallback:', error);
        }
      }
    } catch (error) {
      console.warn('[ChartView PICK] recommendation load failed:', error);
      latestPicks = [];
      latestDate = '';
      quotes = new Map();
    } finally {
      loading = false;
      schedule();
    }
  }

  function ensureStyle() {
    if (document.getElementById('pick-performance-v56-style')) return;
    const style = document.createElement('style');
    style.id = 'pick-performance-v56-style';
    style.textContent = `
      #home-tab .ai-daily-card summary{grid-template-areas:'name score' 'price arrow'!important}
      #home-tab .ai-daily-price{white-space:normal!important;line-height:1.45}
      @media(max-width:700px){
        #home-tab .ai-daily-card summary{grid-template-areas:'name score arrow' 'price score arrow'!important}
      }
    `;
    document.head.appendChild(style);
  }

  function syncHomeSummary() {
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return;

    setText(section.querySelector('.home-watchlist-v30-head span'), 'MY STOCKS · 1달 수익률');
    setText(section.querySelector('[data-home-watch-all]'), '더보기 →');

    const cards = [...section.querySelectorAll('[data-home-watch-open]')];
    cards.forEach((card, index) => {
      const hidden = index >= HOME_VISIBLE;
      card.hidden = hidden;
      card.style.display = hidden ? 'none' : '';
      card.querySelectorAll('.watch-rec-baseline-v55').forEach((node) => node.remove());
      card.querySelector('[data-home-watch-return]')?.classList.remove('no-rec-v55');
    });
  }

  function findPick(card, index) {
    const name = normalize(card.querySelector('.ai-daily-name')?.textContent);
    if (name) {
      const byName = latestPicks.find((row) => normalize(row?.name) === name);
      if (byName) return byName;
    }
    return latestPicks[index] || null;
  }

  function syncPicks() {
    const section = document.getElementById('ai-daily-section');
    if (!section) return;

    section.querySelectorAll('.ai-daily-rank').forEach((rank) => rank.remove());

    const cards = [...section.querySelectorAll('.ai-daily-card')];
    cards.forEach((card, index) => {
      const rec = findPick(card, index);
      if (!rec) return;

      const symbol = String(rec.symbol || '').toUpperCase();
      const recommendedPrice = n(rec.recommendedPrice);
      const currentPrice = quotes.get(symbol) ?? n(rec.currentPrice) ?? recommendedPrice;
      const returnPct = calcReturn(currentPrice, recommendedPrice);
      const priceNode = card.querySelector('.ai-daily-price');
      if (!priceNode || recommendedPrice === null) return;

      priceNode.innerHTML = `추천 종가 ${formatPrice(symbol, recommendedPrice)} → 현재 ${formatPrice(symbol, currentPrice)} · <span class="${returnClass(returnPct)}">${formatReturn(returnPct)}</span>`;
      priceNode.setAttribute('title', `${rec.recommendedDate} 추천 종가 대비 현재가`);
    });

    const subtitle = section.querySelector('.ai-daily-head p');
    if (subtitle && latestDate) {
      const next = subtitle.textContent.replace(/^\d{4}-\d{2}-\d{2}\s+종가 기준/, `${latestDate} 추천 종가 대비 현재가`);
      setText(subtitle, next);
    }
  }

  function observeDom() {
    if (observer && document.body) observer.observe(document.body, { childList: true, subtree: true });
  }

  function sync() {
    queued = false;
    observer?.disconnect();
    ensureStyle();
    syncHomeSummary();
    syncPicks();
    observeDom();
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(sync);
  }

  function boot() {
    ensureStyle();
    if (typeof MutationObserver !== 'undefined') observer = new MutationObserver(schedule);
    observeDom();
    schedule();
    loadPickPerformance();

    document.addEventListener('chartview:watchlist-change', schedule);
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) {
        setTimeout(schedule, 80);
        setTimeout(loadPickPerformance, 120);
      }
    }, true);

    setInterval(loadPickPerformance, REFRESH_MS);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
