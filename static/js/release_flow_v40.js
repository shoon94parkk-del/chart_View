(() => {
  'use strict';
  if (window.__chartViewReleaseFlowV40) return;
  window.__chartViewReleaseFlowV40 = true;

  const NUMERIC_VALUATION_FIELDS = [
    'price','marketCap','forwardPE','forwardEPS','trailingPE','trailingEPS','pbr','bookValue',
    'psr','evEbitda','roe','operatingMargin','dividendYield'
  ];
  let compareLayoutInstalled = false;
  let valueWrapped = false;
  let renderWrapped = false;
  let storageVerifyTimer = null;

  function numberOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    const n = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function sanitizeValuationRows() {
    try {
      if (typeof perData === 'undefined' || !Array.isArray(perData)) return false;
      let changed = false;
      perData.forEach((row) => {
        NUMERIC_VALUATION_FIELDS.forEach((key) => {
          if (!Object.prototype.hasOwnProperty.call(row, key)) return;
          const before = row[key];
          const after = numberOrNull(before);
          const beforeComparable = before === '' || before === undefined || (typeof before === 'number' && !Number.isFinite(before));
          if (beforeComparable || (before !== null && after === null)) {
            row[key] = null;
            changed = true;
          } else if (after !== null && typeof before !== 'number') {
            row[key] = after;
            changed = true;
          }
        });
      });
      return changed;
    } catch (_) { return false; }
  }

  function wrapValuationFormatting() {
    if (!valueWrapped && typeof window.formatValue === 'function') {
      const base = window.formatValue;
      window.formatValue = function (value) {
        const normalized = numberOrNull(value);
        if (normalized === null) return '—';
        const args = [...arguments];
        args[0] = normalized;
        return base.apply(this, args);
      };
      valueWrapped = true;
    }
    if (!renderWrapped && typeof window.renderPerTable === 'function') {
      const base = window.renderPerTable;
      window.renderPerTable = function () {
        sanitizeValuationRows();
        return base.apply(this, arguments);
      };
      renderWrapped = true;
    }
  }

  function compactComparisonLayout() {
    const filter = document.getElementById('global-filter');
    const chartSection = document.querySelector('#chart-tab .chart-section');
    const chartHeader = chartSection?.querySelector('.chart-header');
    const dateSection = document.querySelector('#chart-tab > .date-section');
    if (!filter || !chartSection || !chartHeader) return false;

    if (!filter.querySelector('.v40-compare-heading')) {
      const heading = document.createElement('div');
      heading.className = 'v40-compare-heading';
      heading.innerHTML = '<div><span>COMPARE</span><strong>비교종목 관리</strong></div><small>최대 6개 · 상세 보기와 별도</small>';
      filter.prepend(heading);
    }

    if (dateSection && !chartHeader.querySelector('.v40-chart-periods')) {
      const periods = document.createElement('div');
      periods.className = 'v40-chart-periods';
      const quick = dateSection.querySelector('.quick-periods');
      const custom = dateSection.querySelector('#custom-date-toggle');
      const fields = dateSection.querySelector('#custom-date-fields');
      if (quick) periods.appendChild(quick);
      if (custom) periods.appendChild(custom);
      if (fields) periods.appendChild(fields);
      chartHeader.appendChild(periods);
      dateSection.remove();
    }

    const chartTitle = chartHeader.querySelector('.chart-title');
    if (chartTitle) chartTitle.textContent = '종목별 수익률 비교';
    const chartUnit = chartHeader.querySelector('.chart-unit');
    if (chartUnit) chartUnit.textContent = '기간 시작=0%';
    compareLayoutInstalled = true;
    return true;
  }

  // V40 moves the original period controls into the chart header after chart.js
  // has initialized. Use capture-phase delegation so the controls remain reliable
  // even when the DOM is moved/rebuilt, and keep one explicit period state owner.
  function installChartPeriodDelegation() {
    const tab = document.getElementById('chart-tab');
    if (!tab || tab.dataset.v40PeriodDelegation === '1') return false;
    tab.dataset.v40PeriodDelegation = '1';
    tab.addEventListener('click', (event) => {
      const button = event.target.closest('.period-chip[data-period]');
      if (!button || !tab.contains(button)) return;
      event.preventDefault();
      event.stopImmediatePropagation();

      const period = button.dataset.period;
      if (!period) return;
      tab.querySelectorAll('.period-chip[data-period]').forEach((node) => node.classList.toggle('active', node === button));

      const fields = document.getElementById('custom-date-fields');
      const toggle = document.getElementById('custom-date-toggle');
      const movedWrap = button.closest('.v40-chart-periods');
      movedWrap?.classList.remove('custom-range-open');
      if (fields) fields.hidden = true;
      if (toggle) {
        toggle.setAttribute('aria-expanded', 'false');
        const arrow = toggle.querySelector('.custom-date-arrow');
        if (arrow) arrow.textContent = '⌄';
      }

      try {
        if (period === 'ytd') {
          const today = new Date();
          const start = `${today.getFullYear()}-01-01`;
          const end = typeof localDate === 'function'
            ? localDate(today)
            : `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
          customDateRange = { start, end };
          currentPeriod = '1y';
          const startInput = document.getElementById('start-date');
          const endInput = document.getElementById('end-date');
          if (startInput) startInput.value = start;
          if (endInput) endInput.value = end;
        } else {
          currentPeriod = period;
          customDateRange = null;
        }
        if (typeof loadData === 'function') loadData();
      } catch (error) {
        console.error('[V40] chart period change failed', error);
      }
    }, true);
    return true;
  }

  function verifyWatchlistPersisted() {
    clearTimeout(storageVerifyTimer);
    storageVerifyTimer = setTimeout(() => {
      if (!window.ChartViewState || typeof window.__isWatchlisted !== 'function') return;
      const stored = new Set(window.ChartViewState.getWatchlist().items.map((row) => row.symbol));
      const symbols = new Set();
      document.querySelectorAll('[data-watch-card], [data-home-watch-open]').forEach((node) => {
        const symbol = String(node.dataset.watchCard || node.dataset.homeWatchOpen || '').toUpperCase();
        if (symbol) symbols.add(symbol);
      });
      let mismatch = false;
      symbols.forEach((symbol) => {
        if (Boolean(window.__isWatchlisted(symbol)) !== stored.has(symbol)) mismatch = true;
      });
      if (mismatch) document.dispatchEvent(new CustomEvent('chartview:storage-error', { detail: { key: 'chartview-watchlist-v1', error: 'watchlist persistence mismatch' } }));
    }, 50);
  }

  function normalizeInternalCopy() {
    document.querySelectorAll('.ux-data-status').forEach((node) => {
      node.textContent = (node.textContent || '')
        .replaceAll('adjusted_close', '조정주가')
        .replaceAll('fresh', '정상')
        .replaceAll('stale', '이전값');
    });
    const perSource = document.querySelector('.per-source');
    if (perSource && perSource.textContent.includes('없는 값은 - 표시')) {
      perSource.textContent = perSource.textContent.replace('없는 값은 - 표시', '자료가 없거나 유효하지 않은 값은 — 표시');
    }
  }

  function init() {
    wrapValuationFormatting();
    compactComparisonLayout();
    installChartPeriodDelegation();
    normalizeInternalCopy();
    document.addEventListener('chartview:watchlist-change', verifyWatchlistPersisted);
    document.addEventListener('chartview:compare-change', () => setTimeout(compactComparisonLayout, 0));
    document.addEventListener('click', () => setTimeout(normalizeInternalCopy, 0));
    setTimeout(() => { wrapValuationFormatting(); compactComparisonLayout(); installChartPeriodDelegation(); normalizeInternalCopy(); }, 300);
    setTimeout(() => { wrapValuationFormatting(); compactComparisonLayout(); installChartPeriodDelegation(); }, 1200);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();