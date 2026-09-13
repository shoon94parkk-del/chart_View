(() => {
  'use strict';

  let orderObserver = null;
  let observedHome = null;
  let orderScheduled = false;

  function addStyle(selector, href, datasetKey) {
    if (document.querySelector(selector)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset[datasetKey] = '1';
    document.head.appendChild(link);
  }

  function addScript(selector, src, datasetKey) {
    if (document.querySelector(selector)) return;
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.dataset[datasetKey] = '1';
    document.head.appendChild(script);
  }

  function ensureLegacyVisualAssets() {
    addStyle('link[data-personalization-v36]', '/static/css/personalization_v36.css?v=20260912v36', 'personalizationV36');
    addStyle('link[data-personalized-news-v38]', '/static/css/personalized_news_v38.css?v=20260913v38', 'personalizedNewsV38');
    addStyle('link[data-home-visual-v39]', '/static/css/home_visual_v39.css?v=20260913v39', 'homeVisualV39');
    addStyle('link[data-home-visual-v391]', '/static/css/home_visual_v39_1.css?v=20260913v391', 'homeVisualV391');
    addStyle('link[data-ui-polish-v392]', '/static/css/ui_polish_v39_2.css?v=20260913v392', 'uiPolishV392');
    addStyle('link[data-clarity-v393]', '/static/css/clarity_v39_3.css?v=20260913v393', 'clarityV393');
  }

  function ensureReleaseAssets() {
    addStyle('link[data-release-ui-v40]', '/static/css/release_ui_v40.css?v=20260913stage12', 'releaseUiV40');
    addStyle('link[data-detail-ui-v40]', '/static/css/detail_ui_v40.css?v=20260913v42', 'detailUiV40');
    addStyle('link[data-comparison-ui-v40]', '/static/css/comparison_ui_v40.css?v=20260913stage12', 'comparisonUiV40');
    addStyle('link[data-comparison-compact-v401]', '/static/css/comparison_compact_v40_1.css?v=20260913v401', 'comparisonCompactV401');
    addStyle('link[data-news-status-v401]', '/static/css/news_status_v40_1.css?v=20260913v401', 'newsStatusV401');
    addStyle('link[data-my-hub-v41]', '/static/css/my_hub_v41.css?v=20260913v45', 'myHubV41');
    addStyle('link[data-news-readability-v412]', '/static/css/news_readability_v41_2.css?v=20260913v43', 'newsReadabilityV412');
    addStyle('link[data-resilience-v413]', '/static/css/resilience_v41_3.css?v=20260913v413', 'resilienceV413');
    addStyle('link[data-home-polish-v414]', '/static/css/home_polish_v41_4.css?v=20260913v414', 'homePolishV414');
    addStyle('link[data-home-watchlist-compact-v46]', '/static/css/home_watchlist_compact_v46.css?v=20260913v47', 'homeWatchlistCompactV46');
    addStyle('link[data-home-news-cards-v47]', '/static/css/home_news_cards_v47.css?v=20260913v47', 'homeNewsCardsV47');
    addScript('script[data-app-state-v40]', '/static/js/app_state_v40.js?v=20260913v42', 'appStateV40');
    addScript('script[data-single-detail-v40]', '/static/js/single_detail_v40.js?v=20260913v42', 'singleDetailV40');
    addScript('script[data-detail-visibility-v401]', '/static/js/detail_visibility_v40_1.js?v=20260913v42', 'detailVisibilityV401');
    addScript('script[data-personalized-news-v40]', '/static/js/personalized_news_v40.js?v=20260913v42', 'personalizedNewsV40');
    addScript('script[data-news-status-v401]', '/static/js/news_status_v40_1.js?v=20260913v401', 'newsStatusV401');
    addScript('script[data-release-ui-v40]', '/static/js/release_ui_v40.js?v=20260913v415', 'releaseUiV40');
    addScript('script[data-release-flow-v40]', '/static/js/release_flow_v40.js?v=20260913stage12', 'releaseFlowV40');
    addScript('script[data-comparison-compact-v401]', '/static/js/comparison_compact_v40_1.js?v=20260913v401', 'comparisonCompactV401');
    addScript('script[data-my-hub-v41]', '/static/js/my_hub_v41.js?v=20260913v42', 'myHubV41');
    addScript('script[data-news-readability-v412]', '/static/js/news_readability_v41_2.js?v=20260913v43', 'newsReadabilityV412');
    addScript('script[data-resilience-v413]', '/static/js/resilience_v41_3.js?v=20260913v42', 'resilienceV413');
    addScript('script[data-home-polish-v414]', '/static/js/home_polish_v41_4.js?v=20260913v42', 'homePolishV414');
    addScript('script[data-home-watchlist-compact-v46]', '/static/js/home_watchlist_compact_v46.js?v=20260913v46', 'homeWatchlistCompactV46');
    addScript('script[data-home-news-cards-v47]', '/static/js/home_news_cards_v47.js?v=20260913v47', 'homeNewsCardsV47');
  }

  function ensureAllAssets() { ensureLegacyVisualAssets(); ensureReleaseAssets(); }

  function scheduleOrder() {
    if (orderScheduled) return;
    orderScheduled = true;
    requestAnimationFrame(() => { orderScheduled = false; enforceHomeOrder(); });
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
    if (watchlist) { if (anchor && anchor.nextElementSibling !== watchlist) anchor.insertAdjacentElement('afterend', watchlist); else if (!anchor && home.firstElementChild !== watchlist) home.insertBefore(watchlist, home.firstElementChild); anchor = watchlist; }
    if (news) { if (anchor && anchor.nextElementSibling !== news) anchor.insertAdjacentElement('afterend', news); else if (!anchor && home.firstElementChild !== news) home.insertBefore(news, home.firstElementChild); anchor = news; }
    if (body) { if (anchor && anchor.nextElementSibling !== body) anchor.insertAdjacentElement('afterend', body); else if (!anchor && home.firstElementChild !== body) home.insertBefore(body, home.firstElementChild); anchor = body; }
    if (status) { if (anchor && anchor.nextElementSibling !== status) anchor.insertAdjacentElement('afterend', status); else if (!anchor || status !== home.lastElementChild) home.appendChild(status); status.dataset.homeOrder = 'last'; }
    home.dataset.homeOrder = 'market-watchlist-news-body-status';
    home.dataset.newsVersion = 'v40'; home.dataset.newsPatch = 'v40.1'; home.dataset.visualVersion = 'v39'; home.dataset.uiVersion = 'v40-stage12'; home.dataset.uiPatch = 'v41'; home.dataset.myHubVersion = 'v41'; home.dataset.newsReadability = 'v43'; home.dataset.resilienceVersion = 'v41.3'; home.dataset.homePolish = 'v41.4'; home.dataset.homeDense = 'v47';
    return Boolean(market && body);
  }

  function observeHome() {
    const home = document.querySelector('#home-tab .home-v8');
    if (!home || home === observedHome) return;
    orderObserver?.disconnect(); observedHome = home;
    orderObserver = new MutationObserver(scheduleOrder); orderObserver.observe(home, { childList: true }); scheduleOrder();
  }

  function ensureHome(attempt = 0) {
    ensureAllAssets();
    const existing = document.getElementById('home-watchlist-v30');
    if (!existing && typeof window.__renderHomeWatchlist === 'function') { try { window.__renderHomeWatchlist(); } catch (_) { } }
    observeHome(); enforceHomeOrder();
    const market = document.getElementById('home-market-v9'); const body = document.getElementById('home-v8-body'); const watchlist = document.getElementById('home-watchlist-v30'); const news = document.getElementById('home-personal-news-v37'); const status = document.getElementById('ux12-data-status');
    if ((!market || !body || !watchlist || !news || !status) && attempt < 120) setTimeout(() => ensureHome(attempt + 1), 400);
  }

  function restartSoon() { ensureAllAssets(); setTimeout(() => ensureHome(0), 50); setTimeout(enforceHomeOrder, 300); setTimeout(enforceHomeOrder, 1200); }
  document.addEventListener('chartview:v37-news-rendered', scheduleOrder);
  document.addEventListener('click', (event) => { if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) restartSoon(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restartSoon, { once: true }); else restartSoon();
})();