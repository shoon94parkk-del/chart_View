(() => {
  'use strict';

  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
  const FILTERS = [
    { key: 'none', action: '전체 보기' },
    { key: 'up', action: '상승만 보기' },
    { key: 'rsi35', action: '과매도 보기' },
    { key: 'volume2x', action: '급증만 보기' },
  ];

  function numberFrom(text) {
    const match = String(text || '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function currentRsi35Count() {
    return qsa('#screener-results tbody tr')
      .map((row) => numberFrom(qs('td[data-label="RSI"]', row)?.textContent))
      .filter((value) => Number.isFinite(value) && value <= 35).length;
  }

  function updateActive() {
    const current = typeof window.__getScreenerQuickFilter === 'function'
      ? window.__getScreenerQuickFilter() : 'none';
    qsa('#ux12-screener-kpis .ux13-kpi').forEach((button) => {
      const active = button.dataset.ux13Filter === current;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
      const hint = qs('em', button);
      if (hint) {
        if (active && current !== 'none') hint.textContent = '필터 중';
        else if (button.dataset.ux13Filter === 'none' && current !== 'none') hint.textContent = '필터 해제';
        else hint.textContent = FILTERS.find((item) => item.key === button.dataset.ux13Filter)?.action || '보기';
      }
    });
  }

  function enhanceKpis() {
    const strip = qs('#ux12-screener-kpis');
    if (!strip) return false;

    const legacy = Array.from(strip.children).filter((node) => node.tagName === 'DIV');
    if (legacy.length === 4) {
      const rsi35 = currentRsi35Count();
      legacy.forEach((node, index) => {
        const config = FILTERS[index];
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ux13-kpi';
        button.dataset.ux13Filter = config.key;
        button.innerHTML = node.innerHTML;

        if (config.key === 'rsi35') {
          const label = qs('span', button);
          const value = qs('strong', button);
          if (label) label.textContent = 'RSI 35↓';
          if (value) value.textContent = rsi35.toLocaleString('ko-KR');
        }

        const hint = document.createElement('em');
        hint.textContent = config.action;
        button.appendChild(hint);
        button.setAttribute('aria-label', `${qs('span', button)?.textContent || 'KPI'}: ${config.action}`);
        button.addEventListener('click', () => {
          if (typeof window.__setScreenerQuickFilter === 'function') {
            window.__setScreenerQuickFilter(config.key);
          }
          updateActive();
        });
        node.replaceWith(button);
      });
    }

    updateActive();
    if (strip.dataset.ux13Observed !== '1') {
      strip.dataset.ux13Observed = '1';
      new MutationObserver(() => enhanceKpis()).observe(strip, { childList: true });
    }
    return true;
  }

  function boot() {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (enhanceKpis() || attempts >= 80) clearInterval(timer);
    }, 200);

    document.addEventListener('screener:quickfilter', () => setTimeout(enhanceKpis, 0));
    document.addEventListener('click', (event) => {
      if (event.target.closest('[data-tab="screener"], [data-app-mode="discover"]')) {
        setTimeout(enhanceKpis, 250);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
