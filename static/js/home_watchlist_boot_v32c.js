(() => {
  'use strict';

  let orderObserver = null;
  let observedHome = null;
  let orderScheduled = false;

  function ensureV36Assets() {
    if (!document.querySelector('link[data-personalization-v36]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/personalization_v36.css?v=20260912v36';
      link.dataset.personalizationV36 = '1';
      document.head.appendChild(link);
    }
    if (!document.querySelector('script[data-personalization-v36]')) {
      const script = document.createElement('script');
      script.src = '/static/js/personalization_v36.js?v=20260912v36';
      script.async = false;
      script.dataset.personalizationV36 = '1';
      document.head.appendChild(script);
    }
  }

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

    // V36 canonical Home order:
    // 1) 간단한 시장 현황 -> 2) 내 관심종목 -> 3) 전체 시장/주요 종목 -> 4) 데이터 상태.
    if (market && home.firstElementChild !== market) {
      home.insertBefore(market, home.firstElementChild);
    }

    let anchor = market || null;
    if (watchlist) {
      if (anchor && anchor.nextElementSibling !== watchlist) anchor.insertAdjacentElement('afterend', watchlist);
      else if (!anchor && home.firstElementChild !== watchlist) home.insertBefore(watchlist, home.firstElementChild);
      anchor = watchlist;
    }

    if (body) {
      if (anchor && anchor.nextElementSibling !== body) anchor.insertAdjacentElement('afterend', body);
      else if (!anchor && home.firstElementChild !== body) home.insertBefore(body, home.firstElementChild);
      anchor = body;
    }

    if (status) {
      if (anchor && anchor.nextElementSibling !== status) anchor.insertAdjacentElement('afterend', status);
      else if (!anchor || status !== home.lastElementChild) home.appendChild(status);
      status.dataset.homeOrder = 'last';
    }

    home.dataset.homeOrder = 'market-watchlist-body-status';
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
    ensureV36Assets();
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
    ensureV36Assets();
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
