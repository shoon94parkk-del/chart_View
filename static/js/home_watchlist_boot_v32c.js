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

  function ensureV38Assets() {
    if (!document.querySelector('link[data-personalized-news-v38]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/personalized_news_v38.css?v=20260913v38';
      link.dataset.personalizedNewsV38 = '1';
      document.head.appendChild(link);
    }
    if (!document.querySelector('script[data-personalized-news-v38]')) {
      const script = document.createElement('script');
      script.src = '/static/js/personalized_news_v38.js?v=20260913v38';
      script.async = false;
      script.dataset.personalizedNewsV38 = '1';
      document.head.appendChild(script);
    }
  }

  function ensureV39Assets() {
    if (!document.querySelector('link[data-home-visual-v39]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/home_visual_v39.css?v=20260913v39';
      link.dataset.homeVisualV39 = '1';
      document.head.appendChild(link);
    }
  }

  function ensureV391Assets() {
    if (!document.querySelector('link[data-home-visual-v391]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/home_visual_v39_1.css?v=20260913v391';
      link.dataset.homeVisualV391 = '1';
      document.head.appendChild(link);
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
    const news = document.getElementById('home-personal-news-v37');
    const status = document.getElementById('ux12-data-status');

    if (market && home.firstElementChild !== market) home.insertBefore(market, home.firstElementChild);

    let anchor = market || null;
    if (watchlist) {
      if (anchor && anchor.nextElementSibling !== watchlist) anchor.insertAdjacentElement('afterend', watchlist);
      else if (!anchor && home.firstElementChild !== watchlist) home.insertBefore(watchlist, home.firstElementChild);
      anchor = watchlist;
    }

    if (news) {
      if (anchor && anchor.nextElementSibling !== news) anchor.insertAdjacentElement('afterend', news);
      else if (!anchor && home.firstElementChild !== news) home.insertBefore(news, home.firstElementChild);
      anchor = news;
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

    home.dataset.homeOrder = 'market-watchlist-news-body-status';
    home.dataset.newsVersion = 'v38';
    home.dataset.visualVersion = 'v39';
    home.dataset.visualPatch = 'v39.1';
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
    ensureV38Assets();
    ensureV39Assets();
    ensureV391Assets();
    const existing = document.getElementById('home-watchlist-v30');
    if (!existing && typeof window.__renderHomeWatchlist === 'function') {
      try { window.__renderHomeWatchlist(); } catch (_) { }
    }

    observeHome();
    enforceHomeOrder();

    const market = document.getElementById('home-market-v9');
    const body = document.getElementById('home-v8-body');
    const watchlist = document.getElementById('home-watchlist-v30');
    const news = document.getElementById('home-personal-news-v37');
    const status = document.getElementById('ux12-data-status');

    if ((!market || !body || !watchlist || !news || !status) && attempt < 120) {
      setTimeout(() => ensureWatchlist(attempt + 1), 500);
    }
  }

  function restartSoon() {
    ensureV36Assets();
    ensureV38Assets();
    ensureV39Assets();
    ensureV391Assets();
    setTimeout(() => ensureWatchlist(0), 50);
    setTimeout(enforceHomeOrder, 300);
    setTimeout(enforceHomeOrder, 1200);
  }

  document.addEventListener('chartview:v37-news-rendered', scheduleOrder);
  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) restartSoon();
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restartSoon, { once: true });
  else restartSoon();
})();
