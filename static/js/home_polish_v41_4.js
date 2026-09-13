(() => {
  'use strict';
  if (window.__chartViewHomePolishV414Installed) return;
  window.__chartViewHomePolishV414Installed = true;

  function syncMarketToggle() {
    const panel = document.getElementById('home-market-v9');
    const grid = panel?.querySelector('.home-market-v9-grid');
    if (!panel || !grid) return false;

    let button = panel.querySelector('[data-v415-market-toggle]');

    // Remove every older implementation. V41.5 owns exactly one toggle regardless of load order.
    panel.querySelectorAll('[data-home23-market-toggle], [data-v40-market-more]').forEach((node) => {
      if (node !== button) node.remove();
    });

    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'home23-market-toggle v40-market-more home-v415-market-toggle';
      button.dataset.home23MarketToggle = '1';
      button.dataset.v415MarketToggle = '1';
      grid.insertAdjacentElement('afterend', button);
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const expanded = !panel.classList.contains('home23-expanded');
        panel.classList.toggle('home23-expanded', expanded);
        panel.classList.toggle('v40-market-expanded', expanded);
        syncMarketToggle();
      });
    }

    const total = grid.children.length;
    const hiddenCount = Math.max(0, total - 4);
    if (!hiddenCount) {
      button.hidden = true;
      return true;
    }

    button.hidden = false;
    const expanded = panel.classList.contains('home23-expanded') || panel.classList.contains('v40-market-expanded');
    panel.classList.toggle('home23-expanded', expanded);
    panel.classList.toggle('v40-market-expanded', expanded);
    button.setAttribute('aria-controls', 'home-market-v9-grid');
    button.setAttribute('aria-expanded', String(expanded));
    button.innerHTML = `<span>금리 · VIX · 유가 · 환율</span><strong>${expanded ? '접기' : `${hiddenCount}개 더보기`}</strong>`;
    panel.dataset.marketToggleVersion = 'v41.5';
    return true;
  }

  function decorateWatchlist() {
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return false;
    section.dataset.visualVersion = 'v41.4';
    section.querySelectorAll('[data-home-watch-open]').forEach((button) => {
      if (button.dataset.v414Decorated === '1') return;
      button.dataset.v414Decorated = '1';
      const name = button.dataset.homeWatchName || button.dataset.homeWatchOpen || '관심종목';
      button.setAttribute('aria-label', `${name} 상세 보기`);
    });
    const all = section.querySelector('[data-home-watch-all]');
    if (all) all.setAttribute('aria-label', '관심종목 전체 보기');
    return true;
  }

  function sync() {
    syncMarketToggle();
    decorateWatchlist();
    const home = document.querySelector('#home-tab .home-v8');
    if (home) home.dataset.homePolish = 'v41.5';
  }

  function boot(attempt = 0) {
    const marketReady = syncMarketToggle();
    const watchlistReady = decorateWatchlist();
    if ((!marketReady || !watchlistReady) && attempt < 30) {
      setTimeout(() => boot(attempt + 1), 300);
    }
  }

  document.addEventListener('chartview:v37-news-rendered', () => requestAnimationFrame(sync));
  document.addEventListener('chartview:market-panel-ready', () => requestAnimationFrame(syncMarketToggle));
  document.addEventListener('chartview:watchlist-change', () => requestAnimationFrame(sync));
  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(() => boot(), 50);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => boot(), { once: true });
  } else {
    boot();
  }
})();