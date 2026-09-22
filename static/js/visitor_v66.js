(() => {
  'use strict';

  const VISITOR_KEY = 'chartview-anon-visitor-v66';
  const HEARTBEAT_MS = 20_000;
  let timer = null;

  function visitorId() {
    try {
      let value = localStorage.getItem(VISITOR_KEY);
      if (value) return value;
      value = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : 'cv-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 14);
      localStorage.setItem(VISITOR_KEY, value);
      return value;
    } catch (_) {
      return 'cv-session-' + Math.random().toString(36).slice(2, 14);
    }
  }

  function surface() {
    const button = document.querySelector('.app-bottom-btn.active[data-app-mode]');
    if (button?.dataset?.appMode) return String(button.dataset.appMode).toLowerCase();
    if (document.getElementById('home-tab')?.classList.contains('active')) return 'home';
    if (document.getElementById('watchlist-tab')?.classList.contains('active')) return 'watchlist';
    if (document.getElementById('chart-tab')?.classList.contains('active')) return 'chart';
    return 'other';
  }

  async function heartbeat() {
    if (document.visibilityState !== 'visible' || navigator.onLine === false) return;
    try {
      await fetch('/api/activity', {
        method: 'POST',
        cache: 'no-store',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visitorId: visitorId(), surface: surface() }),
      });
    } catch (_) {
      // Analytics/worker wake-up must never block the app.
    }
  }

  function start() {
    heartbeat();
    timer = setInterval(heartbeat, HEARTBEAT_MS);

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') heartbeat();
    });
    window.addEventListener('online', heartbeat);
    document.addEventListener('click', (event) => {
      if (event.target?.closest?.('.app-bottom-btn[data-app-mode]')) {
        setTimeout(heartbeat, 80);
      }
    });
  }

  window.ChartViewVisitor = Object.freeze({
    version: 'v66',
    heartbeat,
    heartbeatMs: HEARTBEAT_MS,
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
