(() => {
  'use strict';

  let lastAnalysis = 'chart';
  let lastDiscover = 'screener';
  let lastMarket = 'macro';
  let handlingPopState = false;
  let openingAppTab = 0;

  function ensureHomeAssets() {
    if (!document.querySelector('link[data-home-v8]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/home_brief_v8.css?v=20260912v34';
      link.dataset.homeV8 = '1';
      document.head.appendChild(link);
    }
    if (!document.querySelector('script[data-home-v8]')) {
      const script = document.createElement('script');
      script.src = '/static/js/home_brief_v8.js?v=20260912audit1';
      script.async = false;
      script.dataset.homeV8 = '1';
      script.addEventListener('load', () => {
        if (document.querySelector('.app-bottom-nav')) openTab('home', { history: false });
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
    if (state.chartView && state.tab === tabId) return;
    const payload = { chartView: true, tab: tabId };
    try {
      if (replace) history.replaceState(payload, '', location.href);
      else history.pushState(payload, '', location.href);
    } catch (_) { }
  }

  function callLegacySwitch(tabId) {
    if (typeof window.switchTab !== 'function') return;
    openingAppTab += 1;
    try { window.switchTab(tabId); }
    finally { openingAppTab = Math.max(0, openingAppTab - 1); }
  }

  function openTab(tabId, options = {}) {
    const pushHistory = options.history !== false;
    const resolved = tabId === 'market' ? 'macro' : tabId;

    if (resolved === 'home') {
      callLegacySwitch('home');
      if (typeof window.__loadHomeDashboard === 'function') window.__loadHomeDashboard();
      if (pushHistory) commitHistory('home');
      return;
    }
    if (resolved === 'watchlist') {
      if (typeof window.__installWatchlist === 'function') window.__installWatchlist();
      callLegacySwitch('watchlist');
      if (typeof window.__renderWatchlist === 'function') window.__renderWatchlist();
      if (pushHistory) commitHistory('watchlist');
      return;
    }
    if (resolved === 'ideas') {
      const button = document.querySelector('.tab-nav [data-tab="ideas"]');
      if (button) button.click();
      else callLegacySwitch('fwdper');
      if (pushHistory) commitHistory('ideas');
      return;
    }
    if (resolved === 'screener') {
      const button = document.querySelector('.tab-nav [data-tab="screener"]');
      if (button) button.click();
      else callLegacySwitch('screener');
      if (pushHistory) commitHistory('screener');
      return;
    }
    callLegacySwitch(resolved);
    if (resolved === 'revision' && typeof window.__loadRevisionRadar === 'function') {
      window.__loadRevisionRadar();
    }
    if (resolved === 'tools' && typeof window.__installInvestmentTools === 'function') {
      window.__installInvestmentTools();
    }
    if (pushHistory) commitHistory(resolved);
  }

  function wrapSwitchTab() {
    if (typeof window.switchTab !== 'function' || window.__appNavWrapped) return;
    const base = window.switchTab;
    window.switchTab = function (tabId) {
      base(tabId);
      syncNavigation(tabId);
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
      button.addEventListener('click', () => openTab(button.dataset.appTab));
    });
    bottom.querySelectorAll('[data-app-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        const mode = button.dataset.appMode;
        if (button.classList.contains('active')) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        if (mode === 'home') openTab('home');
        else if (mode === 'watchlist') openTab('watchlist');
        else if (mode === 'analysis') openTab(lastAnalysis);
        else if (mode === 'discover') openTab(lastDiscover);
        else if (mode === 'market') openTab(lastMarket);
      });
    });

    document.body.classList.add('app-shell-ready');
    try { history.replaceState({ chartView: true, tab: 'home' }, '', location.href); } catch (_) { }
    if (document.getElementById('home-tab')) openTab('home', { history: false });
    else syncNavigation('chart');
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
    window.addEventListener('popstate', (event) => {
      const tab = event.state?.chartView ? event.state.tab : 'home';
      handlingPopState = true;
      try { openTab(tab || 'home', { history: false }); }
      finally { handlingPopState = false; }
    });
  }

  window.__openAppTab = openTab;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
