(() => {
  'use strict';

  let lastAnalysis = 'chart';
  let lastDiscover = 'screener';

  function ensureHomeAssets() {
    if (!document.querySelector('link[data-home-v8]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/home_brief_v8.css?v=20260911v18';
      link.dataset.homeV8 = '1';
      document.head.appendChild(link);
    }
    if (!document.querySelector('script[data-home-v8]')) {
      const script = document.createElement('script');
      script.src = '/static/js/home_brief_v8.js?v=20260911v22';
      script.async = false;
      script.dataset.homeV8 = '1';
      script.addEventListener('load', () => {
        if (document.querySelector('.app-bottom-nav')) openTab('home');
      }, { once: true });
      document.head.appendChild(script);
    }
  }

  function modeFor(tabId) {
    if (tabId === 'home') return 'home';
    if (tabId === 'tools') return 'tools';
    if (['chart', 'fwdper', 'ideas'].includes(tabId)) return 'analysis';
    if (['screener', 'revision'].includes(tabId)) return 'discover';
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
      nav.hidden = mode === 'home' || nav.dataset.appContext !== mode;
    });
    const shell = document.querySelector('.app-context-shell');
    if (shell) shell.hidden = mode === 'home' || mode === 'tools';

    // 종목 선택 UI는 실제로 종목을 비교하는 '종목분석'에서만 노출한다.
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
  }

  function openTab(tabId) {
    if (tabId === 'home') {
      if (typeof window.switchTab === 'function') window.switchTab('home');
      if (typeof window.__loadHomeDashboard === 'function') window.__loadHomeDashboard();
      return;
    }
    if (tabId === 'ideas') {
      const button = document.querySelector('.tab-nav [data-tab="ideas"]');
      if (button) button.click();
      else if (typeof window.switchTab === 'function') window.switchTab('fwdper');
      return;
    }
    if (tabId === 'screener') {
      const button = document.querySelector('.tab-nav [data-tab="screener"]');
      if (button) button.click();
      else if (typeof window.switchTab === 'function') window.switchTab('screener');
      return;
    }
    if (typeof window.switchTab === 'function') window.switchTab(tabId);
    if (tabId === 'revision' && typeof window.__loadRevisionRadar === 'function') {
      window.__loadRevisionRadar();
    }
  }

  function wrapSwitchTab() {
    if (typeof window.switchTab !== 'function' || window.__appNavWrapped) return;
    const base = window.switchTab;
    window.switchTab = function (tabId) {
      base(tabId);
      syncNavigation(tabId);
      if (tabId === 'home' && typeof window.__loadHomeDashboard === 'function') window.__loadHomeDashboard();
      if (tabId === 'chart' && typeof window.__refreshStockBrief === 'function') window.__refreshStockBrief();
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
      <nav class="app-context-nav app-context-single" data-app-context="market" aria-label="시장 세부 기능" hidden>
        <span class="app-context-title">시장 환경</span>
      </nav>`;
    oldNav.insertAdjacentElement('beforebegin', context);

    const bottom = document.createElement('nav');
    bottom.className = 'app-bottom-nav';
    bottom.setAttribute('aria-label', '주요 메뉴');
    bottom.innerHTML = `
      <button type="button" class="app-bottom-btn active" data-app-mode="home">
        <span class="app-bottom-icon">⌂</span><span>홈</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="analysis">
        <span class="app-bottom-icon">▥</span><span>종목분석</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="discover">
        <span class="app-bottom-icon">⌕</span><span>종목발굴</span>
      </button>
      <button type="button" class="app-bottom-btn" data-app-mode="tools">
        <span class="app-bottom-icon">▦</span><span>도구</span>
      </button>`;
    document.body.appendChild(bottom);

    context.querySelectorAll('[data-app-tab]').forEach((button) => {
      button.addEventListener('click', () => openTab(button.dataset.appTab));
    });
    bottom.querySelectorAll('[data-app-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        const mode = button.dataset.appMode;
        if (mode === 'home') openTab('home');
        else if (mode === 'analysis') openTab(lastAnalysis);
        else if (mode === 'discover') openTab(lastDiscover);
        else if (mode === 'tools') openTab('tools');
        else openTab('macro');
      });
    });

    document.body.classList.add('app-shell-ready');
    if (document.getElementById('home-tab')) openTab('home');
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

  function revealAllDateControls() {
    const section = document.querySelector('.date-section');
    if (!section) return;
    section.classList.add('app-date-visible');
    section.querySelectorAll('.ux-direct-date-toggle').forEach((button) => button.remove());
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
    // Mobile stability: no document.body-wide observer and no rapid polling loop.
    const settle = () => {
      wrapSwitchTab();
      installAppNavigation();
      revealAllValuationMetrics();
      revealAllDateControls();
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
    revealAllDateControls();
    restoreScreenerControls();
    observeLateUI();
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-context-btn')) requestAnimationFrame(keepActiveContextVisible);
    });
  }

  window.__openAppTab = openTab;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
