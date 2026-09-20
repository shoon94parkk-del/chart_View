(() => {
  'use strict';
  if (window.__chartViewWatchlistQuickAddV49) return;
  window.__chartViewWatchlistQuickAddV49 = true;

  const MAX_COMPARE = 6;
  let observer = null;
  let scheduled = false;

  function compareItems() {
    try {
      if (window.ChartViewState?.getCompare) return window.ChartViewState.getCompare().items || [];
    } catch (_) { }
    try {
      if (typeof selectedTickers !== 'undefined' && Array.isArray(selectedTickers)) return [...selectedTickers];
    } catch (_) { }
    try {
      const raw = JSON.parse(localStorage.getItem('chartview-selected-tickers-v1') || '[]');
      return Array.isArray(raw) ? raw : [];
    } catch (_) { return []; }
  }

  function rememberName(symbol, name) {
    try {
      if (window.ChartViewState?.safeWrite && window.ChartViewState?.KEYS?.names) {
        const names = window.ChartViewState.getNames?.() || {};
        names[symbol] = name || symbol;
        window.ChartViewState.safeWrite(window.ChartViewState.KEYS.names, names);
        return;
      }
      const key = 'chartview-ticker-names-v1';
      const names = JSON.parse(localStorage.getItem(key) || '{}');
      names[symbol] = name || symbol;
      localStorage.setItem(key, JSON.stringify(names));
    } catch (_) { }
  }

  function flash(message) {
    let toast = document.getElementById('watchlist-quick-add-toast-v48');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'watchlist-quick-add-toast-v48';
      toast.className = 'watchlist-quick-add-toast-v48';
      toast.setAttribute('role', 'status');
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(flash.timer);
    flash.timer = setTimeout(() => toast.classList.remove('show'), 1500);
  }

  function addToAnalysis(symbol, name) {
    const current = compareItems().map((x) => String(x || '').toUpperCase()).filter(Boolean);
    const key = String(symbol || '').toUpperCase();
    if (!key || current.includes(key)) return;
    if (current.length >= MAX_COMPARE) {
      flash('종목분석은 최대 6개까지 비교할 수 있어요.');
      return;
    }

    rememberName(key, name);
    if (window.ChartViewState?.setCompare) {
      const saved = window.ChartViewState.setCompare([...current, key]);
      if (saved?.ok === false) {
        flash('종목을 추가하지 못했습니다.');
        return;
      }
    } else if (typeof window.addGlobalTicker === 'function') {
      window.addGlobalTicker(key, name || key);
    } else {
      try { localStorage.setItem('chartview-selected-tickers-v1', JSON.stringify([...current, key])); } catch (_) { }
    }
    flash(`${name || key} · 종목분석에 추가했어요.`);
    schedule();
  }

  function syncButtons() {
    const grid = document.getElementById('watchlist-v30-grid');
    if (!grid) return false;
    grid.dataset.quickAddReady = '1';
    const selected = new Set(compareItems().map((x) => String(x || '').toUpperCase()));
    const full = selected.size >= MAX_COMPARE;

    grid.querySelectorAll('[data-watch-card]').forEach((card) => {
      const symbol = String(card.getAttribute('data-watch-card') || '').toUpperCase();
      if (!symbol) return;
      const name = card.querySelector('[data-watch-open]')?.getAttribute('data-watch-open-name') || symbol;
      card.classList.add('has-quick-add-v48');
      let button = card.querySelector('[data-watch-quick-add]');
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'watchlist-quick-add-v48';
        button.setAttribute('data-watch-quick-add', symbol);
        button.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          addToAnalysis(button.getAttribute('data-watch-quick-add'), button.getAttribute('data-watch-quick-name'));
        });
        card.appendChild(button);
      }
      if (button.getAttribute('data-watch-quick-name') !== name) button.setAttribute('data-watch-quick-name', name);
      const active = selected.has(symbol);
      button.classList.toggle('active', active);
      button.classList.toggle('limit', !active && full);
      button.disabled = active;
      const aria = active ? `${name} 종목분석에 포함됨` : `${name} 종목분석에 추가`;
      const label = active ? '✓ 분석에 포함됨' : (full ? '최대 6개' : '+ 종목분석에 추가');
      if (button.getAttribute('aria-label') !== aria) button.setAttribute('aria-label', aria);
      if (button.textContent !== label) button.textContent = label;
    });
    return true;
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      syncButtons();
    });
  }

  function installStyle() {
    if (document.getElementById('watchlist-quick-add-style-v48')) return;
    const style = document.createElement('style');
    style.id = 'watchlist-quick-add-style-v48';
    style.textContent = `
      .watchlist-v33-card.has-quick-add-v48 .watchlist-v33-open,
      .watchlist-v30-card.has-quick-add-v48 .watchlist-v30-open{padding-bottom:52px}
      .watchlist-v33-card.has-quick-add-v48 .watchlist-v33-analysis-link,
      .watchlist-v30-card.has-quick-add-v48 .watchlist-v33-analysis-link{display:none}
      .watchlist-quick-add-v48{position:absolute;left:13px;right:54px;bottom:11px;z-index:3;min-height:30px;padding:0 10px;border:1px solid #d8e8ff;border-radius:9px;background:#edf5ff;color:#1769d2;font:inherit;font-size:10px;font-weight:800;letter-spacing:-.01em;cursor:pointer;white-space:nowrap}
      .watchlist-quick-add-v48:active{transform:translateY(1px);background:#e2efff}
      .watchlist-quick-add-v48.active{border-color:#dfe3e8;background:#f4f6f8;color:#8b95a1;cursor:default}
      .watchlist-quick-add-v48.limit{border-color:#edf0f3;background:#fafbfc;color:#b0b8c1}
      .watchlist-quick-add-toast-v48{position:fixed;left:50%;bottom:86px;z-index:9999;transform:translate(-50%,12px);max-width:calc(100vw - 32px);padding:10px 14px;border-radius:12px;background:rgba(25,31,40,.94);color:#fff;font-size:11px;font-weight:750;box-shadow:0 10px 30px rgba(15,23,42,.2);opacity:0;pointer-events:none;transition:opacity .16s ease,transform .16s ease;white-space:nowrap}
      .watchlist-quick-add-toast-v48.show{opacity:1;transform:translate(-50%,0)}
      @media(max-width:720px){.watchlist-v33-card.has-quick-add-v48 .watchlist-v33-open,.watchlist-v30-card.has-quick-add-v48 .watchlist-v30-open{padding-bottom:50px}.watchlist-quick-add-v48{left:12px;right:52px;bottom:10px;min-height:29px;font-size:10px}}
    `;
    document.head.appendChild(style);
  }

  // The base watchlist is already rendered during app boot. Re-rendering it on
  // every bottom-nav tap used to start another 1-month quote request and made
  // the tab feel slow. Keep the painted DOM and let the explicit refresh button
  // own foreground refreshes; watchlist mutations still call the base renderer.
  function wrapWatchlistRender(attempt = 0) {
    if (window.__watchlistInstantRenderV49) return;
    const base = window.__renderWatchlist;
    if (typeof base !== 'function') {
      if (attempt < 20) setTimeout(() => wrapWatchlistRender(attempt + 1), 80);
      return;
    }
    window.__watchlistInstantRenderV49 = true;
    window.__renderWatchlist = function () {
      const grid = document.getElementById('watchlist-v30-grid');
      if (grid && grid.childElementCount) {
        schedule();
        return grid;
      }
      const result = base.apply(this, arguments);
      schedule();
      return result;
    };
  }

  // Observe only the watchlist grid. The previous body-wide observer woke up on
  // every news-summary/chart mutation and repeatedly scanned the watchlist.
  function attachObserver(attempt = 0) {
    const grid = document.getElementById('watchlist-v30-grid');
    if (!grid) {
      if (attempt < 30) setTimeout(() => attachObserver(attempt + 1), 100);
      return;
    }
    if (observer) observer.disconnect();
    observer = new MutationObserver((mutations) => {
      const meaningful = mutations.some((mutation) => {
        if (mutation.target?.closest?.('[data-watch-quick-add]')) return false;
        return [...mutation.addedNodes, ...mutation.removedNodes].some((node) =>
          node.nodeType === 1 && (!node.matches?.('[data-watch-quick-add]') || node.querySelector?.('[data-watch-card]'))
        );
      });
      if (meaningful) schedule();
    });
    observer.observe(grid, { childList: true, subtree: true });
    schedule();
  }

  function boot() {
    installStyle();
    wrapWatchlistRender();
    attachObserver();
    schedule();
  }

  document.addEventListener('chartview:compare-change', schedule);
  document.addEventListener('chartview:watchlist-change', () => { setTimeout(attachObserver, 0); schedule(); });
  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="watchlist"]')) schedule();
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
