(() => {
  'use strict';

  function applyDenseOverview() {
    try {
      if (typeof METRIC_CONFIG === 'undefined' || !METRIC_CONFIG.overview) return false;
      METRIC_CONFIG.overview.title = '핵심 밸류에이션 한눈에';
      METRIC_CONFIG.overview.description = '전망·실적·자산·매출·수익성을 한 화면에서 먼저 비교하고, 위 세부 지표 탭에서 깊게 확인합니다.';
      METRIC_CONFIG.overview.columns = [
        { key: 'forwardPE', label: 'FWD PER', format: 'number', color: true },
        { key: 'trailingPE', label: 'PER', format: 'number', color: true },
        { key: 'pbr', label: 'PBR', format: 'number', color: true },
        { key: 'psr', label: 'PSR', format: 'number', color: true },
        { key: 'evEbitda', label: 'EV/EBITDA', format: 'number', color: true },
        { key: 'roe', label: 'ROE(%)', format: 'percent', color: true },
        { key: 'operatingMargin', label: '영업이익률(%)', format: 'percent', color: true },
        { key: 'dividendYield', label: '배당률(%)', format: 'percent', color: true },
      ];
      METRIC_CONFIG.overview.barKey = 'forwardPE';
      METRIC_CONFIG.overview.barLabel = 'FWD PER (전망)';
      METRIC_CONFIG.overview.sortKey = 'forwardPE';
      if (typeof currentMetric !== 'undefined' && currentMetric === 'overview' && typeof renderPerTable === 'function') {
        renderPerTable();
      }
      return true;
    } catch (error) {
      console.warn('Dense valuation overview unavailable:', error);
      return false;
    }
  }

  if (!applyDenseOverview()) {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (applyDenseOverview() || attempts >= 20) clearInterval(timer);
    }, 150);
  }
})();
