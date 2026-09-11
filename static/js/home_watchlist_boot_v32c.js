(() => {
  'use strict';

  let stopped = false;

  function tryRender(attempt = 0) {
    if (stopped) return;
    const existing = document.getElementById('home-watchlist-v30');
    if (existing) {
      stopped = true;
      return;
    }

    if (typeof window.__renderHomeWatchlist === 'function') {
      try {
        if (window.__renderHomeWatchlist()) {
          stopped = true;
          return;
        }
      } catch (_) { }
    }

    if (attempt < 120) setTimeout(() => tryRender(attempt + 1), 500);
  }

  function restartSoon() {
    if (document.getElementById('home-watchlist-v30')) return;
    stopped = false;
    setTimeout(() => tryRender(0), 50);
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) restartSoon();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => tryRender(0), { once: true });
  } else {
    tryRender(0);
  }
})();