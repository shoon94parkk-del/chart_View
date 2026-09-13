(() => {
  'use strict';
  if (window.__chartViewHomePolishV414Installed) return;
  window.__chartViewHomePolishV414Installed = true;

  function syncMarketToggle() {
    const panel = document.getElementById('home-market-v9');
    const button = panel?.querySelector('[data-v40-market-more]');
    const grid = panel?.querySelector('.home-market-v9-grid');
    if (!panel || !button || !grid) return false;

    const total = grid.children.length;
    const hiddenCount = Math.max(0, total - 4);
    if (!hiddenCount) {
      button.hidden = true;
      return true;
    }

    button.hidden = false;
    button.setAttribute('aria-controls', 'home-market-v9-grid');
    const expanded = panel.classList.contains('v40-market-expanded');
    button.setAttribute('aria-expanded', String(expanded));
    button.textContent = expanded ? '추가 시장 지표 접기' : `시장 지표 ${hiddenCount}개 더 보기`;
    panel.dataset.marketToggleVersion = 'v41.4';
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
    if (home) home.dataset.homePolish = 'v41.4';
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-v40-market-more]');
    if (!button) return;
    requestAnimationFrame(syncMarketToggle);
  });
  document.addEventListener('chartview:watchlist-change', () => requestAnimationFrame(decorateWatchlist));
  document.addEventListener('chartview:v37-news-rendered', () => requestAnimationFrame(sync));

  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      sync();
    });
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync, { once: true });
  else sync();
})();
