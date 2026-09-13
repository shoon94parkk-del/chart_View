(() => {
  'use strict';
  if (window.__chartViewResilienceV413Installed) return;
  window.__chartViewResilienceV413Installed = true;

  let state = { requestedAt: 0, receivedAt: 0, lastError: null, isStale: false, partialFailures: 0, loading: false };

  const isSafeHttpUrl = (value) => {
    try { const u = new URL(String(value || ''), location.origin); return u.protocol === 'https:' || u.protocol === 'http:'; }
    catch (_) { return false; }
  };
  function timeLabel(ts) { return ts ? new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' }).format(new Date(ts)) : ''; }

  function sanitizeExternalLinks(root = document) {
    root.querySelectorAll('.my-hub-v41-news-row a[target="_blank"], .news-v40-card a[target="_blank"]').forEach((a) => {
      if (!isSafeHttpUrl(a.getAttribute('href'))) { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); a.title = '안전한 원문 주소를 확인할 수 없습니다.'; }
      a.rel = 'noopener noreferrer';
    });
  }
  function improveControls(root = document) {
    root.querySelectorAll('[data-v41-view]').forEach((b) => { b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', b.classList.contains('active') ? 'true' : 'false'); });
    root.querySelector('.my-hub-v41-switch')?.setAttribute('role', 'tablist');
    root.querySelectorAll('[data-v41-sort], [data-v41-symbol]').forEach((b) => b.setAttribute('aria-pressed', b.classList.contains('active') ? 'true' : 'false'));
    root.querySelectorAll('[data-v41-refresh]').forEach((b) => { if (!b.getAttribute('aria-label')) b.setAttribute('aria-label', '관심종목 뉴스 새로고침'); });
  }
  function ensureFreshness(root = document) {
    const head = root.querySelector('.my-hub-v41-news-head');
    if (!head) return;
    let node = head.querySelector('[data-v413-freshness]');
    if (!node) { node = document.createElement('span'); node.className = 'my-hub-v413-freshness'; node.dataset.v413Freshness = '1'; head.querySelector('div')?.appendChild(node); }
    if (!state.receivedAt) node.textContent = state.loading ? '수신 중' : '';
    else node.textContent = `마지막 수신 ${timeLabel(state.receivedAt)}${state.isStale ? ' · 이전 데이터' : ''}${state.partialFailures ? ' · 일부 종목 실패' : ''}`;
  }
  function setRefreshBusy(busy) {
    document.querySelectorAll('[data-v41-refresh]').forEach((b) => { b.disabled = busy; b.setAttribute('aria-busy', busy ? 'true' : 'false'); b.classList.toggle('is-loading', busy); });
  }
  function enhance() {
    sanitizeExternalLinks(); improveControls(); ensureFreshness(); setRefreshBusy(Boolean(state.loading));
    const hub = document.getElementById('watchlist-tab'); if (hub) hub.dataset.resilienceVersion = 'v42';
  }

  document.addEventListener('chartview:v41-news-state', (event) => { state = { ...state, ...(event.detail || {}) }; enhance(); });
  document.addEventListener('chartview:v41-news-rendered', enhance);
  document.addEventListener('chartview:v37-news-rendered', enhance);
  window.addEventListener('offline', () => { document.documentElement.dataset.chartviewOffline = 'true'; const status = document.querySelector('[data-v41-status]'); if (status) status.dataset.offline = 'true'; });
  window.addEventListener('online', () => { delete document.documentElement.dataset.chartviewOffline; const status = document.querySelector('[data-v41-status]'); if (status) delete status.dataset.offline; enhance(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhance, { once: true }); else enhance();
})();
