(() => {
  'use strict';
  if (window.__chartViewResilienceV413Installed) return;
  window.__chartViewResilienceV413Installed = true;

  let feedSnapshot = '';
  let snapshotStatus = '';
  let lastSuccessAt = 0;

  const isSafeHttpUrl = (value) => {
    try {
      const u = new URL(String(value || ''), location.origin);
      return u.protocol === 'https:' || u.protocol === 'http:';
    } catch (_) { return false; }
  };

  function timeLabel(ts) {
    if (!ts) return '';
    return new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' }).format(new Date(ts));
  }

  function sanitizeExternalLinks(root = document) {
    root.querySelectorAll('.my-hub-v41-news-row a[target="_blank"], .news-v40-card a[target="_blank"]').forEach((a) => {
      if (!isSafeHttpUrl(a.getAttribute('href'))) {
        a.removeAttribute('href');
        a.setAttribute('aria-disabled', 'true');
        a.title = '안전한 원문 주소를 확인할 수 없습니다.';
      }
      a.rel = 'noopener noreferrer';
    });
  }

  function improveControls(root = document) {
    root.querySelectorAll('[data-v41-view]').forEach((b) => {
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', b.classList.contains('active') ? 'true' : 'false');
    });
    root.querySelector('.my-hub-v41-switch')?.setAttribute('role', 'tablist');
    root.querySelectorAll('[data-v41-sort], [data-v41-symbol]').forEach((b) => {
      b.setAttribute('aria-pressed', b.classList.contains('active') ? 'true' : 'false');
    });
    root.querySelectorAll('[data-v41-refresh]').forEach((b) => {
      if (!b.getAttribute('aria-label')) b.setAttribute('aria-label', '관심종목 뉴스 새로고침');
    });
  }

  function ensureFreshness(root = document) {
    const head = root.querySelector('.my-hub-v41-news-head');
    if (!head) return;
    let node = head.querySelector('[data-v413-freshness]');
    if (!node) {
      node = document.createElement('span');
      node.className = 'my-hub-v413-freshness';
      node.dataset.v413Freshness = '1';
      head.querySelector('div')?.appendChild(node);
    }
    if (lastSuccessAt) node.textContent = `마지막 갱신 ${timeLabel(lastSuccessAt)}`;
  }

  function setRefreshBusy(busy) {
    document.querySelectorAll('[data-v41-refresh]').forEach((b) => {
      b.disabled = busy;
      b.setAttribute('aria-busy', busy ? 'true' : 'false');
      b.classList.toggle('is-loading', busy);
    });
  }

  function captureBeforeRefresh() {
    const feed = document.querySelector('[data-v41-feed]');
    const status = document.querySelector('[data-v41-status]');
    if (feed?.children.length) {
      feedSnapshot = feed.innerHTML;
      snapshotStatus = status?.textContent || '';
    }
    setRefreshBusy(true);
  }

  function monitorStatus() {
    const status = document.querySelector('[data-v41-status]');
    const feed = document.querySelector('[data-v41-feed]');
    if (!status || !feed) return;
    const text = status.textContent || '';
    const loading = text.includes('불러오는 중');
    setRefreshBusy(loading);

    if (text.includes('불러오지 못했습니다') && !feed.children.length && feedSnapshot) {
      feed.innerHTML = feedSnapshot;
      status.innerHTML = `<strong>새 뉴스 갱신에 실패했습니다.</strong> <span>기존 뉴스를 계속 표시합니다.</span>`;
      status.dataset.stale = 'true';
      sanitizeExternalLinks(feed);
      improveControls(feed);
      return;
    }

    if (/건 중 \d+건 표시/.test(text)) {
      lastSuccessAt = Date.now();
      status.dataset.stale = 'false';
      feedSnapshot = feed.innerHTML;
      snapshotStatus = text;
      ensureFreshness();
    }
  }

  function enhance() {
    sanitizeExternalLinks();
    improveControls();
    ensureFreshness();
    monitorStatus();
    const hub = document.getElementById('watchlist-tab');
    if (hub) hub.dataset.resilienceVersion = 'v41.3';
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-v41-refresh]')) captureBeforeRefresh();
  }, true);
  window.addEventListener('offline', () => {
    const status = document.querySelector('[data-v41-status]');
    if (status) status.textContent = '오프라인 상태입니다. 기존 화면은 유지되며 연결 후 새로고침할 수 있습니다.';
  });
  window.addEventListener('online', enhance);

  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; enhance(); });
  });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  document.addEventListener('DOMContentLoaded', enhance, { once: true });
  enhance();
})();