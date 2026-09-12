(() => {
  'use strict';

  let orderObserver = null;
  let observedHome = null;
  let orderScheduled = false;

  function scheduleOrder() {
    if (orderScheduled) return;
    orderScheduled = true;
    requestAnimationFrame(() => {
      orderScheduled = false;
      enforceHomeOrder();
    });
  }

  function enforceHomeOrder() {
    const home = document.querySelector('#home-tab .home-v8');
    if (!home) return false;

    const market = document.getElementById('home-market-v9');
    const body = document.getElementById('home-v8-body');
    const watchlist = document.getElementById('home-watchlist-v30');
    const status = document.getElementById('ux12-data-status');

    // Canonical Home order:
    // 1) 오늘의 시장 -> 2) 주요 시황/시장 요약 -> 3) 내 관심종목 -> 4) 데이터 상태
    if (market && home.firstElementChild !== market) {
      home.insertBefore(market, home.firstElementChild);
    }

    let anchor = market || null;
    if (body) {
      if (anchor && anchor.nextElementSibling !== body) anchor.insertAdjacentElement('afterend', body);
      else if (!anchor && home.firstElementChild !== body) home.insertBefore(body, home.firstElementChild);
      anchor = body;
    }

    if (watchlist) {
      if (anchor && anchor.nextElementSibling !== watchlist) anchor.insertAdjacentElement('afterend', watchlist);
      else if (!anchor) home.appendChild(watchlist);
      anchor = watchlist;
    }

    if (status) {
      if (anchor && anchor.nextElementSibling !== status) anchor.insertAdjacentElement('afterend', status);
      else if (!anchor || status !== home.lastElementChild) home.appendChild(status);
      status.dataset.homeOrder = 'last';
    }

    home.dataset.homeOrder = 'market-body-watchlist-status';
    return Boolean(market && body);
  }

  function observeHome() {
    const home = document.querySelector('#home-tab .home-v8');
    if (!home || home === observedHome) return;
    if (orderObserver) orderObserver.disconnect();
    observedHome = home;
    orderObserver = new MutationObserver(scheduleOrder);
    orderObserver.observe(home, { childList: true });
    scheduleOrder();
  }

  function ensureWatchlist(attempt = 0) {
    const existing = document.getElementById('home-watchlist-v30');
    if (!existing && typeof window.__renderHomeWatchlist === 'function') {
      try { window.__renderHomeWatchlist(); } catch (_) { }
    }

    observeHome();
    enforceHomeOrder();

    const market = document.getElementById('home-market-v9');
    const body = document.getElementById('home-v8-body');
    const watchlist = document.getElementById('home-watchlist-v30');
    const status = document.getElementById('ux12-data-status');

    if ((!market || !body || !watchlist || !status) && attempt < 120) {
      setTimeout(() => ensureWatchlist(attempt + 1), 500);
    }
  }

  function restartSoon() {
    setTimeout(() => ensureWatchlist(0), 50);
    setTimeout(enforceHomeOrder, 300);
    setTimeout(enforceHomeOrder, 1200);
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) restartSoon();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', restartSoon, { once: true });
  } else {
    restartSoon();
  }
})();