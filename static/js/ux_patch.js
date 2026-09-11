// UX/performance patch: fast screener + instant Korean stock search + mobile refinements.
(() => {
  'use strict';

  function ensureStyle(selector, href, datasetKey) {
    if (document.querySelector(selector)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset[datasetKey] = '1';
    document.head.appendChild(link);
  }

  function ensureScript(selector, src, datasetKey) {
    if (document.querySelector(selector)) return;
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.dataset[datasetKey] = '1';
    document.head.appendChild(script);
  }

  ensureStyle('link[data-fast-screener]', '/static/css/screener.css?v=20260911v3', 'fastScreener');
  ensureScript('script[data-fast-screener]', '/static/js/screener.js?v=20260911v1', 'fastScreener');
  ensureStyle('link[data-ideas-ui]', '/static/css/ideas.css?v=20260911v1', 'ideasUi');
  ensureScript('script[data-valuation-meta]', '/static/js/valuation_meta.js?v=20260911v1', 'valuationMeta');
  ensureScript('script[data-investment-ideas]', '/static/js/ideas.js?v=20260911v1', 'investmentIdeas');
  ensureScript('script[data-dense-valuation]', '/static/js/valuation_overview_v4.js?v=20260911v4', 'denseValuation');
  ensureStyle('link[data-ux-v3]', '/static/css/ux_v3.css?v=20260911v4', 'uxV3');
  ensureScript('script[data-revision-radar]', '/static/js/revision_radar.js?v=20260911v3', 'revisionRadar');
  ensureScript('script[data-ux-v3]', '/static/js/ux_v3.js?v=20260911v5', 'uxV3');
  ensureStyle('link[data-bottom-nav-v6]', '/static/css/bottom_nav_v6.css?v=20260911v6', 'bottomNavV6');
  ensureStyle('link[data-decision-ux-v7]', '/static/css/decision_ux_v7.css?v=20260911v7', 'decisionUxV7');
  ensureScript('script[data-decision-ux-v7]', '/static/js/decision_ux_v7.js?v=20260911v7', 'decisionUxV7');
  ensureStyle('link[data-app-header-v5]', '/static/css/app_header_v5.css?v=20260911v5', 'appHeaderV5');
  ensureScript('script[data-app-header-v5]', '/static/js/app_header_v5.js?v=20260911v5', 'appHeaderV5');
  ensureStyle('link[data-home-market-v9]', '/static/css/home_market_v9.css?v=20260911v10', 'homeMarketV9');
  ensureScript('script[data-home-market-v9]', '/static/js/home_market_v9.js?v=20260911v10', 'homeMarketV9');
  ensureStyle('link[data-home-priority-v10]', '/static/css/home_priority_v10.css?v=20260911v10', 'homePriorityV10');
  ensureScript('script[data-home-priority-v10]', '/static/js/home_priority_v10.js?v=20260911v10', 'homePriorityV10');
  ensureStyle('link[data-valuation-matrix-v10]', '/static/css/valuation_matrix_v10.css?v=20260911v10', 'valuationMatrixV10');

  const aliases = {
    '삼전': '삼성전자', '하닉': 'SK하이닉스', '삼바': '삼성바이오로직스',
    '엘전': 'LG전자', '현차': '현대차', '네이버': 'NAVER', 'naver': 'NAVER',
    'jyp': 'JYP Ent.', 'jypent': 'JYP Ent.', 'jyp ent': 'JYP Ent.',
    'jyp entertainment': 'JYP Ent.'
  };

  let universePromise = null;
  let localTimer = null;

  const hasKorean = (text) => /[가-힣]/.test(text);
  const isSixCharCode = (text) => /^\d{6}$/.test(text);
  const isTickerLike = (text) => /^[A-Z][A-Z0-9.^=-]{0,11}$/.test(String(text || '').trim().toUpperCase());

  function loadUniverse() {
    if (!universePromise) {
      universePromise = fetch('/static/data/screener.json', { cache: 'force-cache' })
        .then((res) => {
          if (!res.ok) throw new Error(`screener HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          const rows = Array.isArray(data.stocks) ? data.stocks : [];
          window.__KRX_UNIVERSE__ = rows;
          return rows;
        })
        .catch((err) => {
          console.warn('Local Korean universe unavailable; falling back to server search.', err);
          return [];
        });
    }
    return universePromise;
  }

  function normalizeQuery(raw) {
    const q = raw.trim();
    return aliases[q.toLowerCase()] || q;
  }

  function wantsLocalSearch(raw) {
    const q = raw.trim();
    return hasKorean(q) || isSixCharCode(q) || Object.prototype.hasOwnProperty.call(aliases, q.toLowerCase());
  }

  function rankKorean(rows, raw) {
    const query = normalizeQuery(raw);
    const q = query.toLowerCase();
    return rows
      .map((row) => {
        const name = String(row.name || '');
        const code = String(row.code || '');
        const nameLower = name.toLowerCase();
        let score = -1;
        if (code.toLowerCase() === q || nameLower === q) score = 100;
        else if (nameLower.startsWith(q)) score = 80;
        else if (nameLower.includes(q)) score = 60;
        else if (code.toLowerCase().startsWith(q)) score = 50;
        return { row, score };
      })
      .filter((x) => x.score >= 0)
      .sort((a, b) => b.score - a.score || (b.row.avgValue20 || 0) - (a.row.avgValue20 || 0))
      .slice(0, 10)
      .map((x) => x.row);
  }

  function renderLocalResults(rows, raw) {
    const box = document.getElementById('search-results');
    if (!box) return;
    if (!rows.length) {
      box.innerHTML = `<div class="search-result-item"><span class="name">검색 결과 없음</span><span class="symbol">${raw}</span></div>`;
      box.classList.remove('hidden');
      return;
    }
    box.innerHTML = '';
    rows.forEach((row) => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = '<span class="name"></span><span class="symbol"></span>';
      item.querySelector('.name').textContent = row.name || row.symbol;
      item.querySelector('.symbol').textContent = `${row.code || row.symbol} · ${row.market || 'KRX'}`;
      item.addEventListener('click', () => {
        if (typeof window.selectSearchResult === 'function') window.selectSearchResult(row.symbol, row.name || row.symbol);
      });
      box.appendChild(item);
    });
    box.classList.remove('hidden');
  }

  async function addBestLocal(raw) {
    const rows = rankKorean(await loadUniverse(), raw);
    if (rows[0] && typeof window.selectSearchResult === 'function') {
      window.selectSearchResult(rows[0].symbol, rows[0].name || rows[0].symbol);
      return true;
    }
    return false;
  }

  function enhanceValuationTable() {
    const table = document.querySelector('#per-table-container .per-table');
    if (!table) return;
    const headers = Array.from(table.querySelectorAll('thead th')).map((th) => th.textContent.trim());
    if (!headers.length) return;
    table.querySelectorAll('tbody tr').forEach((row) => {
      Array.from(row.children).forEach((cell, index) => { cell.dataset.label = headers[index] || ''; });
      const name = row.querySelector('.stock-name')?.textContent?.trim();
      const ticker = row.querySelector('.stock-ticker')?.textContent?.trim();
      if (name || ticker) row.setAttribute('aria-label', [name, ticker].filter(Boolean).join(' '));
    });
  }

  function watchValuationTable() {
    const container = document.getElementById('per-table-container');
    if (!container) return;
    enhanceValuationTable();
    const observer = new MutationObserver(() => enhanceValuationTable());
    observer.observe(container, { childList: true, subtree: true });
  }

  function fitMainChart() {
    const container = document.getElementById('chart-container');
    if (!container) return;
    const height = window.innerWidth <= 720 ? 300 : 340;
    container.style.height = `${height}px`;
    try {
      if (typeof chart !== 'undefined' && chart) {
        chart.resize(container.clientWidth, height);
        chart.applyOptions({ handleScale: { mouseWheel: false, pinch: true } });
      }
    } catch (_) { }
  }

  function enhanceTabUX() {
    const nav = document.querySelector('.tab-nav');
    if (!nav) return;
    if (typeof window.switchTab === 'function' && !window.__chartViewSwitchWrapped) {
      const baseSwitch = window.switchTab;
      window.switchTab = function (tabId) {
        baseSwitch(tabId);
        const globalFilter = document.getElementById('global-filter');
        if (globalFilter) globalFilter.style.display = ['chart', 'fwdper', 'ideas'].includes(tabId) ? 'block' : 'none';
      };
      window.__chartViewSwitchWrapped = true;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadUniverse();
    watchValuationTable();
    enhanceTabUX();
    setTimeout(fitMainChart, 0);
    window.addEventListener('resize', fitMainChart, { passive: true });

    const sector = document.querySelector('.sector-section');
    if (sector && !sector.querySelector('.ux-sector-toggle')) {
      const toggle = document.createElement('button');
      toggle.className = 'ux-sector-toggle';
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', 'true');
      toggle.innerHTML = '<span>추천 종목</span><span class="ux-sector-arrow">접기 ↑</span>';
      sector.insertBefore(toggle, sector.firstChild);
      toggle.addEventListener('click', () => {
        const collapsed = sector.classList.toggle('ux-collapsed');
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.querySelector('.ux-sector-arrow').textContent = collapsed ? '펼치기 ↓' : '접기 ↑';
      });
    }

    const chartHeader = document.querySelector('.chart-header');
    if (chartHeader && !document.querySelector('.ux-data-status')) {
      const status = document.createElement('div');
      status.className = 'ux-data-status';
      status.textContent = '차트: Yahoo Finance 실시간 요청 · 스크리너: 한국 장마감 배치 · 밸류에이션: 실시간 시세 + 일일 컨센서스 캐시';
      chartHeader.insertAdjacentElement('afterend', status);
    }

    const input = document.getElementById('unified-input');
    const box = document.getElementById('search-results');
    const addButton = document.getElementById('add-btn');
    if (!input || !box) return;
    input.setAttribute('aria-label', '종목명, 6자리 종목코드 또는 해외 티커 검색');

    input.addEventListener('input', (event) => {
      const raw = input.value.trim();
      if (!wantsLocalSearch(raw)) return;
      event.stopImmediatePropagation();
      clearTimeout(localTimer);
      if (!raw) {
        box.classList.add('hidden');
        return;
      }
      localTimer = setTimeout(async () => renderLocalResults(rankKorean(await loadUniverse(), raw), raw), 60);
    }, true);

    input.addEventListener('keypress', (event) => {
      const raw = input.value.trim();
      if (event.key !== 'Enter' || !wantsLocalSearch(raw)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      addBestLocal(raw).then((added) => { if (added) input.value = ''; });
    }, true);

    if (addButton) {
      addButton.addEventListener('click', (event) => {
        const raw = input.value.trim();
        if (!wantsLocalSearch(raw)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        addBestLocal(raw).then((added) => { if (added) input.value = ''; });
      }, true);
    }

    input.addEventListener('input', (event) => {
      const raw = input.value.trim();
      if (!isTickerLike(raw) || wantsLocalSearch(raw)) return;
      event.stopImmediatePropagation();
      const symbol = raw.toUpperCase();
      box.innerHTML = '';
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = '<span class="name">티커로 바로 추가</span><span class="symbol"></span>';
      item.querySelector('.symbol').textContent = symbol;
      item.addEventListener('click', () => {
        if (typeof window.selectSearchResult === 'function') window.selectSearchResult(symbol, symbol);
      });
      box.appendChild(item);
      box.classList.remove('hidden');
    }, true);
  });
})();