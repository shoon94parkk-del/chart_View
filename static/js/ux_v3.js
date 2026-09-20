(() => {
  'use strict';

  let lastAnalysis = 'chart';
  let lastDiscover = 'screener';
  let lastMarket = 'macro';
  let handlingPopState = false;
  let openingAppTab = 0;
  let userNavigationStarted = false;

  const ROUTE_TABS = new Set(['home', 'watchlist', 'chart', 'fwdper', 'ideas', 'screener', 'revision', 'macro', 'tools']);

  function resolveInitialRoute() {
    let params = null;
    try { params = new URLSearchParams(window.location.search); } catch (_) { }
    const requestedTab = params?.get('tab');
    const symbol = String(params?.get('symbol') || '').trim().toUpperCase();
    const name = String(params?.get('name') || '').trim();
    if (requestedTab && ROUTE_TABS.has(requestedTab)) {
      return { tab: requestedTab, explicit: true, view: params?.get('view') || '', symbol, name, scrollY: 0 };
    }
    if (symbol) return { tab: 'chart', explicit: true, view: 'detail', symbol, name, scrollY: 0 };
    // A new/reloaded visit to the clean root URL always starts at Home.
    // history.state is restored only by the popstate handler for in-app Back/Forward.
    return { tab: 'home', explicit: false, view: '', symbol: '', name: '', scrollY: 0 };
  }

  function cleanRouteUrl() {
    try {
      const url = new URL(location.href);
      ['tab', 'view', 'symbol', 'name'].forEach((key) => url.searchParams.delete(key));
      return `${url.pathname}${url.search}${url.hash}`;
    } catch (_) {
      return location.pathname || '/';
    }
  }

  function rememberCurrentScroll() {
    if (!history.state?.chartView) return;
    try {
      history.replaceState({ ...history.state, scrollY: Math.max(0, Math.round(window.scrollY || 0)) }, '', location.href);
    } catch (_) { }
  }

  function restoreScroll(scrollY) {
    const top = Math.max(0, Number(scrollY) || 0);
    requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo({ top, behavior: 'auto' })));
  }

  function openInitialDetail(route, attempt = 0) {
    if (!route?.symbol) return;
    if (typeof window.__openStockDetail === 'function') {
      window.__openStockDetail(route.symbol, route.name || route.symbol, { history: false, instant: true });
      return;
    }
    if (attempt < 60) setTimeout(() => openInitialDetail(route, attempt + 1), 50);
  }

  function applyInitialRoute(route, attempt = 0) {
    const target = document.getElementById(`${route.tab}-tab`);
    if (!target) {
      if (attempt < 160) setTimeout(() => applyInitialRoute(route, attempt + 1), 50);
      return false;
    }
    openTab(route.tab, { history: false });
    if (route.symbol) openInitialDetail(route);
    else restoreScroll(route.scrollY);
    return true;
  }

  function ensureHomeAssets() {
    if (!document.querySelector('link[data-home-v8]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/home_brief_v8.css?v=20260912v35';
      link.dataset.homeV8 = '1';
      document.head.appendChild(link);
    }
    if (!document.querySelector('script[data-home-v8]')) {
      const script = document.createElement('script');
      script.src = '/static/js/home_brief_v8.js?v=20260912v35';
      script.async = false;
      script.dataset.homeV8 = '1';
      script.addEventListener('load', () => {
        // Initial route ownership lives in installAppNavigation().
        // Loading Home assets must never redirect the current screen.
      }, { once: true });
      document.head.appendChild(script);
    }
  }

  function modeFor(tabId) {
    if (tabId === 'home') return 'home';
    if (tabId === 'watchlist') return 'watchlist';
    if (['chart', 'fwdper', 'ideas'].includes(tabId)) return 'analysis';
    if (['screener', 'revision'].includes(tabId)) return 'discover';
    if (['macro', 'tools'].includes(tabId)) return 'market';
    return 'market';
  }

  function syncNavigation(tabId) {
    const mode = modeFor(tabId);
    document.querySelectorAll('[data-app-mode]').forEach((button) => {
      button.classList.toggle('active', button.dataset.appMode === mode);
      button.setAttribute('aria-current', button.dataset.appMode === mode ? 'page' : 'false');
    });
    document.querySelectorAll('[data-app-tab]').forEach((button) => {
      button.classList.toggle('active', button.dataset.appTab === tabId);
    });
    document.querySelectorAll('.app-context-nav').forEach((nav) => {
      nav.hidden = mode === 'home' || mode === 'watchlist' || nav.dataset.appContext !== mode;
    });
    const shell = document.querySelector('.app-context-shell');
    if (shell) shell.hidden = mode === 'home' || mode === 'watchlist';

    const utilityHeader = document.querySelector('.header');
    if (utilityHeader) {
      const showStockSearch = mode === 'analysis';
      utilityHeader.hidden = !showStockSearch;
      utilityHeader.style.setProperty('display', showStockSearch ? 'block' : 'none', 'important');
    }
    const globalFilter = document.getElementById('global-filter');
    if (globalFilter) globalFilter.style.display = mode === 'analysis' ? 'block' : 'none';

    if (mode === 'analysis') lastAnalysis = tabId;
    if (mode === 'discover') lastDiscover = tabId;
    if (mode === 'market') lastMarket = tabId;
  }

  function commitHistory(tabId, replace = false) {
    if (handlingPopState || !window.history?.pushState) return;
    const state = history.state || {};
    if (!replace && state.chartView && state.tab === tabId && !state.view) return;
    if (!replace) rememberCurrentScroll();
    const payload = { chartView: true, tab: tabId, scrollY: 0 };
    const url = cleanRouteUrl();
    try {
      if (replace) history.replaceState(payload, '', url);
      else history.pushState(payload, '', url);
    } catch (_) { }
  }

  function callLegacySwitch(tabId) {
    if (typeof window.switchTab !== 'function') return;
    openingAppTab += 1;
    try { window.switchTab(tabId); }
    finally { openingAppTab = Math.max(0, openingAppTab - 1); }
  }

  function activateTabBody(tabId) {
    const target = document.getElementById(`${tabId}-tab`);
    if (!target) return false;
    document.querySelectorAll('.tab-content').forEach((content) => {
      const active = content === target;
      content.classList.toggle('active', active);
      content.style.display = active ? 'block' : 'none';
    });
    document.querySelectorAll('.tab-btn').forEach((button) => {
      button.classList.toggle('active', button.dataset.tab === tabId);
    });
    return true;
  }

  function scheduleChartResize(tabId) {
    if (tabId !== 'chart') return;
    const resize = () => window.dispatchEvent(new Event('resize'));
    requestAnimationFrame(() => {
      requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    });
    setTimeout(resize, 80);

    const ensure = (attempt = 0) => {
      const active = document.getElementById('chart-tab')?.classList.contains('active');
      if (!active) return;
      if (!document.body.classList.contains('app-booting') && typeof window.__ensureChartVisible === 'function') {
        window.__ensureChartVisible();
        return;
      }
      if (attempt < 40) setTimeout(() => ensure(attempt + 1), 50);
    };
    ensure();
  }

  function openTab(tabId, options = {}) {
    const pushHistory = options.history !== false;
    const resolved = tabId === 'market' ? 'macro' : tabId;

    if (resolved === 'home') {
      callLegacySwitch('home');
      activateTabBody('home');
      syncNavigation('home');
      if (typeof window.__loadHomeDashboard === 'function') window.__loadHomeDashboard();
      if (pushHistory) commitHistory('home');
      return;
    }
    if (resolved === 'watchlist') {
      if (typeof window.__installWatchlist === 'function') window.__installWatchlist();
      callLegacySwitch('watchlist');
      activateTabBody('watchlist');
      syncNavigation('watchlist');
      if (typeof window.__renderWatchlist === 'function') window.__renderWatchlist();
      if (pushHistory) commitHistory('watchlist');
      return;
    }
    if (resolved === 'ideas') {
      const button = document.querySelector('.tab-nav [data-tab="ideas"]');
      if (button) button.click();
      else callLegacySwitch('fwdper');
      activateTabBody('ideas');
      syncNavigation('ideas');
      if (pushHistory) commitHistory('ideas');
      return;
    }
    if (resolved === 'screener') {
      const button = document.querySelector('.tab-nav [data-tab="screener"]');
      if (button) button.click();
      else callLegacySwitch('screener');
      activateTabBody('screener');
      syncNavigation('screener');
      if (pushHistory) {
        commitHistory('screener');
        window.__openScreenerDiscoveryView?.();
        window.__openScreenerAtTop?.();
      }
      return;
    }
    callLegacySwitch(resolved);
    activateTabBody(resolved);
    syncNavigation(resolved);
    scheduleChartResize(resolved);
    if (resolved === 'revision' && typeof window.__loadRevisionRadar === 'function') {
      window.__loadRevisionRadar();
    }
    if (resolved === 'tools' && typeof window.__installInvestmentTools === 'function') {
      window.__installInvestmentTools();
    }
    if (pushHistory) commitHistory(resolved);
  }

  function navigateUserTab(tabId) {
    const resolved = tabId === 'market' ? 'macro' : tabId;
    const leavingDetail = Boolean(window.ChartViewState?.detail?.open || history.state?.view === 'detail');
    if (!leavingDetail) return openTab(tabId);
    if (typeof window.__closeStockDetail === 'function') window.__closeStockDetail({ force: true, restore: false });
    openTab(tabId, { history: false });
    try { history.replaceState({ chartView: true, tab: resolved }, '', location.href); } catch (_) { }
  }

  function wrapSwitchTab() {
    if (typeof window.switchTab !== 'function' || window.__appNavWrapped) return;
    const base = window.switchTab;
    window.switchTab = function (tabId) {
      base(tabId);
      activateTabBody(tabId);
      syncNavigation(tabId);
      scheduleChartResize(tabId);
      if (tabId === 'home' && typeof window.__loadHomeDashboard === 'function') window.__loadHomeDashboard();
      if (tabId === 'chart' && typeof window.__refreshStockBrief === 'function') window.__refreshStockBrief();
      if (tabId === 'watchlist' && typeof window.__renderWatchlist === 'function') window.__renderWatchlist();
      if (!openingAppTab && !handlingPopState && tabId) commitHistory(tabId);
    };
    window.__appNavWrapped = true;
  }

  function installAppNavigation() {
    if (document.querySelector('.app-bottom-nav')) return;
    const oldNav = document.querySelector('.tab-nav');
    if (!oldNav) return;

    const context = document.createElement('div');
    context.className = 'app-context-shell';
    context.innerHTML = `
      <nav class="app-context-nav" data-app-context="analysis" aria-label="종목 분석 세부 기능" hidden>
        <button type="button" class="app-context-btn active" data-app-tab="chart">차트</button>
        <button type="button" class="app-context-btn" data-app-tab="fwdper">밸류에이션</button>
        <button type="button" class="app-context-btn" data-app-tab="ideas">투자판단</button>
      </nav>
      <nav class="app-context-nav" data-app-context="discover" aria-label="종목 발굴 세부 기능" hidden>
        <button type="button" class="app-context-btn active" data-app-tab="screener">스크리너</button>
        <button type="button" class="app-context-btn" data-app-tab="revision">실적·괴리</button>
      </nav>
      <nav class="app-context-nav" data-app-context="market" aria-label="시장 세부 기능" hidden>
        <button type="button" class="app-context-btn active" data-app-tab="macro">시장지표</button>
        <button type="button" class="app-context-btn" data-app-tab="tools">투자도구</button>
      </nav>`;
    oldNav.insertAdjacentElement('beforebegin', context);

    const bottom = document.createElement('nav');
    bottom.className = 'app-bottom-nav';
    bottom.setAttribute('aria-label', '주요 메뉴');
    bottom.innerHTML = `
      <button type="button" class="app-bottom-btn active" data-app-mode="home">
        <span class="app-bottom-icon">⌂</span><span>홈</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="watchlist">
        <span class="app-bottom-icon">☆</span><span>관심</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="analysis">
        <span class="app-bottom-icon">▥</span><span>종목분석</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="discover">
        <span class="app-bottom-icon">⌕</span><span>종목발굴</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="market">
        <span class="app-bottom-icon">▦</span><span>시장</span>
      </button>`;
    document.body.appendChild(bottom);

    context.querySelectorAll('[data-app-tab]').forEach((button) => {
      button.addEventListener('click', () => {
        userNavigationStarted = true;
        navigateUserTab(button.dataset.appTab);
      });
    });
    bottom.querySelectorAll('[data-app-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        userNavigationStarted = true;
        const mode = button.dataset.appMode;
        const visibleTab = [...document.querySelectorAll('.tab-content')].find((tab) => {
          const style = getComputedStyle(tab);
          return !tab.hidden && tab.getAttribute('aria-hidden') !== 'true' && style.display !== 'none' && style.visibility !== 'hidden';
        });
        const visibleTabId = visibleTab?.id?.replace(/-tab$/, '') || '';
        const actualMode = visibleTabId ? modeFor(visibleTabId) : '';
        if (button.classList.contains('active') && actualMode === mode && !window.ChartViewState?.detail?.open) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        const targetTab = mode === 'home' ? 'home'
          : mode === 'watchlist' ? 'watchlist'
          : mode === 'analysis' ? lastAnalysis
          : mode === 'discover' ? 'screener'
          : lastMarket;

        const jumpDiscoverTop = () => {
          const scroller = document.scrollingElement || document.documentElement;
          scroller.scrollTop = 0;
          document.documentElement.scrollTop = 0;
          if (document.body) document.body.scrollTop = 0;
        };
        if (mode === 'discover') jumpDiscoverTop();
        navigateUserTab(targetTab);
        if (mode === 'discover') {
          window.__openScreenerDiscoveryView?.();
          jumpDiscoverTop();
          requestAnimationFrame(jumpDiscoverTop);
          [40, 100, 220].forEach((delay) => setTimeout(jumpDiscoverTop, delay));
        }

        // The legacy switch function is installed by a DOMContentLoaded handler.
        // Keep navigation state correct even when a user taps before its wrapper runs.
        syncNavigation(targetTab === 'market' ? 'macro' : targetTab);
      });
    });

    document.body.classList.add('app-shell-ready');
    const route = resolveInitialRoute();
    const payload = {
      ...(history.state || {}),
      chartView: true,
      tab: route.tab,
      scrollY: route.scrollY,
    };
    if (route.view) payload.view = route.view;
    if (route.symbol) payload.symbol = route.symbol;
    if (route.name) payload.name = route.name;
    try { history.replaceState(payload, '', route.explicit ? location.href : cleanRouteUrl()); } catch (_) { }

    // Home/watchlist are installed by later modules in the same deferred bundle.
    // Keep route ownership here and wait for the requested tab instead of letting
    // those modules redirect the user when they finish loading.
    applyInitialRoute(route);
  }

  function revealAllValuationMetrics() {
    const section = document.querySelector('.metric-section');
    if (!section) return;
    section.classList.remove('ux-metrics-open');
    section.querySelectorAll('.ux-advanced-metric').forEach((button) => button.classList.remove('ux-advanced-metric'));
    section.querySelectorAll('.ux-more-metrics').forEach((button) => button.remove());
    section.dataset.uxSimplified = '0';
  }

  function restoreScreenerControls() {
    const controls = document.querySelector('#screener-tab .screener-controls');
    if (!controls) return;

    const advanced = controls.querySelector('.ux-screener-advanced');
    const quick = controls.querySelector('.ux-screener-quick');
    if (advanced || quick) {
      const body = advanced?.querySelector('.ux-screener-advanced-body');
      const mainRow = controls.querySelector('.screener-main-row');
      if (body) {
        const marketRow = body.querySelector('[data-screen-market]')?.closest('.screener-row');
        if (marketRow) controls.appendChild(marketRow);
        const selects = body.querySelector('.ux-screener-selects');
        if (selects && mainRow) selects.querySelectorAll('select').forEach((select) => mainRow.appendChild(select));
        const presetRow = body.querySelector('[data-screen-preset]')?.closest('.screener-row');
        if (presetRow) controls.appendChild(presetRow);
      }
      if (quick) {
        const row = document.createElement('div');
        row.className = 'screener-row screen-scroll-row app-restored-presets';
        quick.querySelectorAll('[data-screen-preset]').forEach((button) => row.appendChild(button));
        controls.appendChild(row);
        quick.remove();
      }
      advanced?.remove();
    }
    controls.dataset.uxSimplified = '0';
  }

  function keepActiveContextVisible() {
    const active = document.querySelector('.app-context-btn.active');
    active?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }

  function observeLateUI() {
    const settle = () => {
      wrapSwitchTab();
      installAppNavigation();
      revealAllValuationMetrics();
      restoreScreenerControls();
    };
    queueMicrotask(settle);
    setTimeout(settle, 350);
    setTimeout(settle, 1200);
  }

  function init() {
    ensureHomeAssets();
    wrapSwitchTab();
    installAppNavigation();
    revealAllValuationMetrics();
    restoreScreenerControls();
    observeLateUI();
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-context-btn')) requestAnimationFrame(keepActiveContextVisible);
    });
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    window.addEventListener('popstate', (event) => {
      const state = event.state?.chartView ? event.state : { tab: 'home', scrollY: 0 };
      const tab = ROUTE_TABS.has(state.tab) ? state.tab : 'home';
      userNavigationStarted = true;
      handlingPopState = true;
      try {
        if (state.view === 'detail' && state.symbol) {
          openTab('chart', { history: false });
          openInitialDetail({ tab: 'chart', symbol: state.symbol, name: state.name || state.symbol });
        } else {
          if (typeof window.__closeStockDetail === 'function' && window.ChartViewState?.detail?.open) {
            window.__closeStockDetail({ force: true, restore: false });
          }
          openTab(tab, { history: false });
          restoreScroll(state.scrollY);
        }
      } finally { handlingPopState = false; }
    });
  }

  window.__openAppTab = function (tabId, options = {}) {
    userNavigationStarted = true;
    return openTab(tabId, options);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
