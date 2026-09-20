(() => {
  'use strict';
  if (window.__chartViewHomeWatchlistCompactV46Installed) return;
  window.__chartViewHomeWatchlistCompactV46Installed = true;

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const QUOTE_CACHE_KEY = 'chartview-watchlist-quotes-v33';
  const RECENTS_KEY = 'chartview-recents-v1';
  const MOBILE_QUERY = '(max-width: 720px)';
  const mql = window.matchMedia(MOBILE_QUERY);
  let observer = null;
  let observedSection = null;
  let scheduled = false;

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function safeJson(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || 'null');
      return value == null ? fallback : value;
    } catch (_) { return fallback; }
  }

  function watchlistRows() {
    if (window.ChartViewState?.getWatchlist) return window.ChartViewState.getWatchlist().items.slice(0, 16);
    const rows = safeJson(WATCHLIST_KEY, []);
    return Array.isArray(rows) ? rows.slice(0, 16) : [];
  }

  function quoteMap() {
    const cache = safeJson(QUOTE_CACHE_KEY, { quotes: {} });
    return cache && typeof cache === 'object' && cache.quotes && typeof cache.quotes === 'object' ? cache.quotes : {};
  }

  function marketLabel(symbol) { return /\.(KS|KQ)$/.test(symbol) ? 'KR' : 'US'; }

  function formatPrice(symbol, value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    if (/\.(KS|KQ)$/.test(symbol)) return `₩${Math.round(n).toLocaleString('ko-KR')}`;
    return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function returnClass(value) {
    const n = Number(value);
    return n > 0 ? 'up' : n < 0 ? 'down' : 'flat';
  }

  function returnText(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  }

  function recordRecent(symbol, name) {
    try {
      const existing = safeJson(RECENTS_KEY, []);
      const rows = Array.isArray(existing) ? existing : [];
      const next = [{ symbol, name }, ...rows.filter((row) => String(row?.symbol || '').toUpperCase() !== symbol)].slice(0, 8);
      localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
    } catch (_) { }
  }

  function openAnalysis(symbol, name) {
    recordRecent(symbol, name);
    if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
    else if (typeof window.switchTab === 'function') window.switchTab('chart');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function renderCompact() {
    if (!mql.matches) return false;
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return false;

    const rows = watchlistRows();
    const quotes = quoteMap();
    const currentCards = section.querySelectorAll('[data-home-watch-open]');
    const alreadyCompact = currentCards.length === rows.length && [...currentCards].every((card) => card.classList.contains('home-watch-compact-v46'));
    if (alreadyCompact) return true;

    section.dataset.compactVersion = 'v46';
    section.innerHTML = `
      <div class="home-block-head home-watchlist-v30-head">
        <div><span>MY STOCKS · 가격 / 1달 수익률</span><h3>내 관심종목</h3></div>
        <button type="button" data-home-watch-all>전체보기 →</button>
      </div>
      ${rows.length ? `<div class="home-watchlist-v30-chips">${rows.map((row) => {
        const symbol = String(row.symbol || '').toUpperCase();
        const name = String(row.name || symbol);
        const quote = quotes[symbol] || {};
        const cls = returnClass(quote.return);
        return `<button type="button" class="home-watch-compact-v46" data-home-watch-open="${esc(symbol)}" data-home-watch-name="${esc(name)}" aria-label="${esc(name)} 상세 보기">
          <span class="home-watch-v33-top"><strong>${esc(name)}</strong><i>${marketLabel(symbol)}</i></span>
          <small>${esc(symbol)}</small>
          <span class="home-watch-v33-quote"><b data-home-watch-price>${formatPrice(symbol, quote.price)}</b><em class="${cls}" data-home-watch-return><span>1달</span> ${returnText(quote.return)}</em></span>
        </button>`;
      }).join('')}</div>` : '<div class="home-watchlist-v30-empty"><strong>관심종목을 추가해 보세요</strong><span>가격과 1달 수익률을 홈에서 바로 확인할 수 있습니다.</span></div>'}`;

    section.querySelector('[data-home-watch-all]')?.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('watchlist');
    });
    section.querySelectorAll('[data-home-watch-open]').forEach((button) => button.addEventListener('click', () => {
      openAnalysis(button.dataset.homeWatchOpen, button.dataset.homeWatchName);
    }));
    return true;
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      attach();
      renderCompact();
    });
  }

  function attach() {
    const section = document.getElementById('home-watchlist-v30');
    if (!section || section === observedSection) return Boolean(section);
    observer?.disconnect();
    observedSection = section;
    observer = new MutationObserver(schedule);
    observer.observe(section, { childList: true });
    return true;
  }

  function boot(attempt = 0) {
    if (attach()) renderCompact();
    else if (attempt < 40) setTimeout(() => boot(attempt + 1), 250);
  }

  mql.addEventListener?.('change', (event) => {
    if (event.matches) schedule();
    else if (typeof window.__renderHomeWatchlist === 'function') {
      try { window.__renderHomeWatchlist(); } catch (_) { }
    }
  });

  document.addEventListener('chartview:watchlist-change', schedule);
  document.addEventListener('chartview:v37-news-rendered', schedule);
  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(schedule, 60);
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), { once: true });
  else boot();
})();
