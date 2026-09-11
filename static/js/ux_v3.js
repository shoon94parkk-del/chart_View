(() => {
  'use strict';

  let lastAnalysis = 'chart';
  let lastDiscover = 'screener';

  function activeMode(tabId) {
    if (['chart', 'fwdper', 'ideas'].includes(tabId)) return 'analysis';
    if (['screener', 'revision'].includes(tabId)) return 'discover';
    return 'market';
  }

  function syncNav(tabId) {
    const mode = activeMode(tabId);
    document.querySelectorAll('[data-ux-mode]').forEach((button) => {
      button.classList.toggle('active', button.dataset.uxMode === mode);
    });
    document.querySelectorAll('[data-ux-tab]').forEach((button) => {
      button.classList.toggle('active', button.dataset.uxTab === tabId);
    });
    document.querySelectorAll('.ux-subnav').forEach((nav) => {
      nav.hidden = nav.dataset.uxSubnav !== mode;
    });

    if (mode === 'analysis') lastAnalysis = tabId;
    if (mode === 'discover') lastDiscover = tabId;
  }

  function openTab(tabId) {
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
    if (typeof window.switchTab !== 'function' || window.__uxV3Wrapped) return;
    const base = window.switchTab;
    window.switchTab = function (tabId) {
      base(tabId);
      syncNav(tabId);
    };
    window.__uxV3Wrapped = true;
  }

  function installPrimaryNav() {
    if (document.querySelector('.ux-primary-shell')) return;
    const oldNav = document.querySelector('.tab-nav');
    if (!oldNav) return;

    const shell = document.createElement('div');
    shell.className = 'ux-primary-shell';
    shell.innerHTML = `
      <nav class="ux-primary-nav" aria-label="주요 기능">
        <button type="button" class="ux-primary-btn active" data-ux-mode="analysis">📊 종목 분석</button>
        <button type="button" class="ux-primary-btn" data-ux-mode="discover">🔎 종목 발굴</button>
        <button type="button" class="ux-primary-btn" data-ux-mode="market">🌐 시장</button>
      </nav>
      <nav class="ux-subnav" data-ux-subnav="analysis" aria-label="종목 분석 기능">
        <button type="button" class="ux-sub-btn active" data-ux-tab="chart">차트</button>
        <button type="button" class="ux-sub-btn" data-ux-tab="fwdper">밸류에이션</button>
        <button type="button" class="ux-sub-btn" data-ux-tab="ideas">투자판단</button>
      </nav>
      <nav class="ux-subnav" data-ux-subnav="discover" aria-label="종목 발굴 기능" hidden>
        <button type="button" class="ux-sub-btn active" data-ux-tab="screener">추천 스크리너</button>
        <button type="button" class="ux-sub-btn" data-ux-tab="revision">실적 상향</button>
      </nav>`;

    oldNav.insertAdjacentElement('beforebegin', shell);

    shell.querySelectorAll('[data-ux-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        const mode = button.dataset.uxMode;
        if (mode === 'analysis') openTab(lastAnalysis);
        else if (mode === 'discover') openTab(lastDiscover);
        else openTab('macro');
      });
    });

    shell.querySelectorAll('[data-ux-tab]').forEach((button) => {
      button.addEventListener('click', () => openTab(button.dataset.uxTab));
    });

    document.body.classList.add('ux-v3-ready');
    syncNav('chart');
  }

  function simplifyDateControls() {
    const section = document.querySelector('.date-section');
    const row = section?.querySelector('.date-row');
    if (!section || !row || section.dataset.uxSimplified === '1') return;
    section.dataset.uxSimplified = '1';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ux-direct-date-toggle';
    button.textContent = '직접 기간 설정';
    button.setAttribute('aria-expanded', 'false');
    row.insertAdjacentElement('beforebegin', button);

    button.addEventListener('click', () => {
      const open = section.classList.toggle('ux-date-open');
      button.setAttribute('aria-expanded', String(open));
      button.textContent = open ? '직접 기간 닫기' : '직접 기간 설정';
    });

    row.querySelector('#apply-date-btn')?.addEventListener('click', () => {
      section.classList.remove('ux-date-open');
      button.setAttribute('aria-expanded', 'false');
      button.textContent = '직접 기간 설정';
    });
  }

  function simplifyMetricControls() {
    const section = document.querySelector('.metric-section');
    const chips = section?.querySelector('.metric-chips');
    if (!section || !chips || section.dataset.uxSimplified === '1') return;
    section.dataset.uxSimplified = '1';

    const primary = new Set(['overview', 'fwd_per', 'pbr', 'profitability']);
    chips.querySelectorAll('.metric-chip').forEach((button) => {
      if (!primary.has(button.dataset.metric)) button.classList.add('ux-advanced-metric');
    });

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'ux-more-metrics';
    toggle.textContent = '상세 지표 더보기';
    toggle.setAttribute('aria-expanded', 'false');
    chips.insertAdjacentElement('afterend', toggle);

    toggle.addEventListener('click', () => {
      const open = section.classList.toggle('ux-metrics-open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? '상세 지표 접기' : '상세 지표 더보기';
    });
  }

  function simplifyScreener() {
    const controls = document.querySelector('#screener-tab .screener-controls');
    if (!controls || controls.dataset.uxSimplified === '1') return;
    controls.dataset.uxSimplified = '1';

    const mainRow = controls.querySelector('.screener-main-row');
    const marketRow = controls.querySelector('[data-screen-market]')?.closest('.screener-row');
    const presetButtons = Array.from(controls.querySelectorAll('[data-screen-preset]'));
    const quickButtons = presetButtons.filter((button) => ['candidate', 'momentum', 'oversold'].includes(button.dataset.screenPreset));
    const advancedButtons = presetButtons.filter((button) => !['candidate', 'momentum', 'oversold'].includes(button.dataset.screenPreset));
    const valueSelect = document.getElementById('screener-value');
    const sortSelect = document.getElementById('screener-sort');

    const quick = document.createElement('div');
    quick.className = 'ux-screener-quick';
    const quickLabel = document.createElement('span');
    quickLabel.className = 'ux-control-label';
    quickLabel.textContent = '빠른 조건';
    quick.appendChild(quickLabel);
    quickButtons.forEach((button) => quick.appendChild(button));

    const details = document.createElement('details');
    details.className = 'ux-screener-advanced';
    details.innerHTML = '<summary>고급 필터</summary><div class="ux-screener-advanced-body"></div>';
    const body = details.querySelector('.ux-screener-advanced-body');

    if (marketRow) body.appendChild(marketRow);

    if (valueSelect || sortSelect) {
      const selects = document.createElement('div');
      selects.className = 'ux-screener-selects';
      if (valueSelect) selects.appendChild(valueSelect);
      if (sortSelect) selects.appendChild(sortSelect);
      body.appendChild(selects);
    }

    if (advancedButtons.length) {
      const row = document.createElement('div');
      row.className = 'screener-row screen-scroll-row';
      advancedButtons.forEach((button) => row.appendChild(button));
      body.appendChild(row);
    }

    if (mainRow) {
      mainRow.querySelectorAll('select').forEach((select) => select.remove());
      mainRow.insertAdjacentElement('afterend', quick);
      quick.insertAdjacentElement('afterend', details);
    } else {
      controls.prepend(quick);
      controls.appendChild(details);
    }
  }

  function observeLateUI() {
    let attempts = 0;
    const timer = setInterval(() => {
      wrapSwitchTab();
      installPrimaryNav();
      simplifyScreener();
      attempts += 1;
      if (attempts >= 12) clearInterval(timer);
    }, 250);

    const observer = new MutationObserver(() => {
      simplifyScreener();
      if (document.querySelector('.tab-nav [data-tab="ideas"]')) wrapSwitchTab();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 5000);
  }

  function init() {
    wrapSwitchTab();
    installPrimaryNav();
    simplifyDateControls();
    simplifyMetricControls();
    setTimeout(simplifyScreener, 600);
    observeLateUI();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
