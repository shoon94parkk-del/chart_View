(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const RECENTS_KEY = 'chartview-recents-v1';
  const SELECTED_KEY = 'chartview-selected-tickers-v1';
  const NAME_KEY = 'chartview-ticker-names-v1';
  const MAX_WATCHLIST = 20;
  const DEFAULT_WATCHLIST = [
    { symbol: '005930.KS', name: '삼성전자' },
    { symbol: 'NVDA', name: '엔비디아' },
    { symbol: 'AAPL', name: '애플' },
  ];

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const safeParse = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) { return fallback; }
  };

  const normalize = (row) => {
    if (!row) return null;
    const symbol = String(row.symbol || row.ticker || '').trim().toUpperCase();
    if (!symbol) return null;
    return { symbol, name: String(row.name || symbol).trim() || symbol };
  };

  let watchlist = safeParse(WATCHLIST_KEY, DEFAULT_WATCHLIST).map(normalize).filter(Boolean).slice(0, MAX_WATCHLIST);
  let recents = safeParse(RECENTS_KEY, []).map(normalize).filter(Boolean).slice(0, 8);
  let quoteSeq = 0;
  let searchTimer = null;

  function dedupe(rows) {
    const seen = new Set();
    return rows.filter((row) => row && row.symbol && !seen.has(row.symbol) && seen.add(row.symbol));
  }

  watchlist = dedupe(watchlist);
  recents = dedupe(recents);

  function saveWatchlist() {
    try { localStorage.setItem(WATCHLIST_KEY, JSON.stringify(watchlist)); } catch (_) { }
  }

  function saveRecents() {
    try { localStorage.setItem(RECENTS_KEY, JSON.stringify(recents)); } catch (_) { }
  }

  function saveNameMap() {
    try {
      const names = {};
      if (typeof tickerNameMap !== 'undefined') Object.assign(names, tickerNameMap);
      localStorage.setItem(NAME_KEY, JSON.stringify(names));
    } catch (_) { }
  }

  function knownName(symbol, fallback) {
    try {
      if (typeof tickerNameMap !== 'undefined' && tickerNameMap[symbol]) return tickerNameMap[symbol];
    } catch (_) { }
    const hit = watchlist.find((x) => x.symbol === symbol) || recents.find((x) => x.symbol === symbol);
    return hit?.name || fallback || symbol;
  }

  function restoreSelection() {
    const saved = safeParse(SELECTED_KEY, null);
    const names = safeParse(NAME_KEY, {});
    try {
      if (Array.isArray(saved) && saved.length) {
        selectedTickers = saved.map((x) => String(x).trim().toUpperCase()).filter(Boolean).slice(0, 6);
        if (typeof perTickers !== 'undefined') perTickers = [...selectedTickers];
      }
      if (names && typeof names === 'object') {
        if (typeof tickerNameMap !== 'undefined') Object.assign(tickerNameMap, names);
        if (typeof perTickerNameMap !== 'undefined') Object.assign(perTickerNameMap, names);
      }
    } catch (_) { }
  }

  function persistSelection() {
    try {
      if (typeof selectedTickers !== 'undefined') localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedTickers.slice(0, 6)));
      saveNameMap();
    } catch (_) { }
  }

  function isWatchlisted(symbol) {
    const key = String(symbol || '').toUpperCase();
    return watchlist.some((x) => x.symbol === key);
  }

  function recordRecent(symbol, name) {
    const row = normalize({ symbol, name: name || knownName(symbol) });
    if (!row) return;
    recents = [row, ...recents.filter((x) => x.symbol !== row.symbol)].slice(0, 8);
    saveRecents();
    renderRecents();
  }

  function toggleWatchlist(symbol, name) {
    const row = normalize({ symbol, name: name || knownName(symbol) });
    if (!row) return false;
    const index = watchlist.findIndex((x) => x.symbol === row.symbol);
    if (index >= 0) watchlist.splice(index, 1);
    else {
      if (watchlist.length >= MAX_WATCHLIST) {
        alert(`관심종목은 최대 ${MAX_WATCHLIST}개까지 저장할 수 있어요.`);
        return false;
      }
      watchlist.unshift(row);
    }
    saveWatchlist();
    document.dispatchEvent(new CustomEvent('chartview:watchlist-change'));
    render();
    renderHomeShortcut();
    enhanceTickerStars();
    return index < 0;
  }

  function formatPrice(symbol, value) {
    const price = Number(value);
    if (!Number.isFinite(price)) return '-';
    if (/\.(KS|KQ)$/.test(symbol)) return `₩${Math.round(price).toLocaleString('ko-KR')}`;
    return `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function returnClass(value) {
    const n = Number(value);
    return n > 0 ? 'up' : n < 0 ? 'down' : 'flat';
  }

  function returnText(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  }

  function renderHomeShortcut() {
    const body = document.getElementById('home-v8-body');
    if (!body) return false;
    let section = document.getElementById('home-watchlist-v30');
    if (!section) {
      section = document.createElement('section');
      section.id = 'home-watchlist-v30';
      section.className = 'home-v8-block home-watchlist-v30';
      body.insertAdjacentElement('beforebegin', section);
    }
    const visible = watchlist.slice(0, 4);
    section.innerHTML = `
      <div class="home-block-head home-watchlist-v30-head">
        <div><span>MY STOCKS</span><h3>내 관심종목</h3></div>
        <button type="button" data-home-watch-all>전체보기 →</button>
      </div>
      ${visible.length ? `<div class="home-watchlist-v30-chips">${visible.map((row) => `<button type="button" data-home-watch-open="${esc(row.symbol)}" data-home-watch-name="${esc(row.name)}"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)}</small></button>`).join('')}</div>` : '<p class="home-watchlist-v30-empty">관심종목을 추가하면 홈에서 바로 이동할 수 있습니다.</p>'}`;
    section.querySelector('[data-home-watch-all]')?.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('watchlist');
    });
    section.querySelectorAll('[data-home-watch-open]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.homeWatchOpen, button.dataset.homeWatchName)));
    return true;
  }

  function installTab() {
    let tab = document.getElementById('watchlist-tab');
    if (tab) return tab;
    const anchor = document.getElementById('macro-tab') || document.getElementById('chart-tab');
    if (!anchor) return null;
    tab = document.createElement('div');
    tab.id = 'watchlist-tab';
    tab.className = 'tab-content watchlist-tab-v30';
    anchor.insertAdjacentElement('beforebegin', tab);
    tab.innerHTML = `
      <main class="watchlist-v30">
        <header class="watchlist-v30-head">
          <div><span class="watchlist-v30-eyebrow">MY STOCKS</span><h2>관심종목</h2><p>관심종목과 최근 본 종목을 이 기기에 저장합니다.</p></div>
          <span class="watchlist-v30-count" data-watch-count>0개</span>
        </header>
        <section class="watchlist-v30-searchbox">
          <div class="watchlist-v30-searchrow"><input id="watchlist-v30-search" type="search" placeholder="종목명 · 6자리 코드 · 해외 티커로 관심종목 추가" autocomplete="off"></div>
          <div id="watchlist-v30-search-results" class="watchlist-v30-search-results"></div>
        </section>
        <section class="watchlist-v30-section">
          <div class="watchlist-v30-section-head"><h3>내 관심종목</h3><small>누르면 종목분석으로 이동</small></div>
          <div id="watchlist-v30-grid" class="watchlist-v30-grid"></div>
        </section>
        <section class="watchlist-v30-section">
          <div class="watchlist-v30-section-head"><h3>최근 본 종목</h3><small>최대 8개</small></div>
          <div id="watchlist-v30-recents" class="watchlist-v30-recents"></div>
        </section>
        <p class="watchlist-v30-footer-note">관심종목은 현재 기기의 브라우저 저장소에 보관됩니다. 추후 앱 계정 기능을 추가하면 기기 간 동기화할 수 있습니다.</p>
      </main>`;
    bindSearch(tab);
    return tab;
  }

  function renderSearchResults(rows) {
    const box = document.getElementById('watchlist-v30-search-results');
    if (!box) return;
    if (!rows.length) {
      box.innerHTML = '<div class="watchlist-v30-search-item"><span><strong>검색 결과가 없습니다.</strong><small>해외 종목은 정확한 티커를 입력해 보세요.</small></span></div>';
      box.classList.add('show');
      return;
    }
    box.innerHTML = rows.slice(0, 8).map((row) => {
      const symbol = esc(row.symbol);
      const name = esc(row.name || row.symbol);
      return `<button type="button" class="watchlist-v30-search-item" data-watch-search-symbol="${symbol}" data-watch-search-name="${name}"><span><strong>${name}</strong><small>${esc(row.market ? `${row.code || row.symbol} · ${row.market}` : row.symbol)}</small></span><b>${isWatchlisted(row.symbol) ? '저장됨' : '+ 추가'}</b></button>`;
    }).join('');
    box.classList.add('show');
    box.querySelectorAll('[data-watch-search-symbol]').forEach((button) => button.addEventListener('click', () => {
      toggleWatchlist(button.dataset.watchSearchSymbol, button.dataset.watchSearchName);
      const input = document.getElementById('watchlist-v30-search');
      if (input) input.value = '';
      box.classList.remove('show');
    }));
  }

  function bindSearch(tab) {
    const input = tab.querySelector('#watchlist-v30-search');
    const box = tab.querySelector('#watchlist-v30-search-results');
    if (!input || !box) return;
    input.addEventListener('input', () => {
      clearTimeout(searchTimer);
      const q = input.value.trim();
      if (!q) { box.classList.remove('show'); box.innerHTML = ''; return; }
      searchTimer = setTimeout(async () => {
        try {
          const response = await fetch(`/api/search?q=${encodeURIComponent(q)}`, { cache: 'no-store' });
          const data = response.ok ? await response.json() : { results: [] };
          let rows = Array.isArray(data.results) ? data.results : [];
          if (!rows.length && /^[A-Za-z][A-Za-z0-9.^=-]{0,11}$/.test(q)) rows = [{ symbol: q.toUpperCase(), name: q.toUpperCase() }];
          renderSearchResults(rows);
        } catch (_) { renderSearchResults([]); }
      }, 180);
    });
  }

  function renderRecents() {
    const root = document.getElementById('watchlist-v30-recents');
    if (!root) return;
    if (!recents.length) {
      root.innerHTML = '<span class="watchlist-v30-footer-note">아직 최근 본 종목이 없습니다.</span>';
      return;
    }
    root.innerHTML = recents.map((row) => `<button type="button" class="watchlist-v30-recent ${isWatchlisted(row.symbol) ? 'in-watch' : ''}" data-watch-recent="${esc(row.symbol)}" data-watch-recent-name="${esc(row.name)}">${esc(row.name)}</button>`).join('');
    root.querySelectorAll('[data-watch-recent]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.watchRecent, button.dataset.watchRecentName)));
  }

  function render() {
    const tab = installTab();
    if (!tab) return;
    const count = tab.querySelector('[data-watch-count]');
    if (count) count.textContent = `${watchlist.length}개`;
    const grid = tab.querySelector('#watchlist-v30-grid');
    if (!grid) return;
    if (!watchlist.length) {
      grid.innerHTML = '<div class="watchlist-v30-empty"><strong>관심종목이 비어 있습니다.</strong><p>위 검색창이나 종목분석의 ☆ 버튼에서 종목을 저장해 보세요.</p></div>';
      renderRecents();
      return;
    }
    grid.innerHTML = watchlist.map((row) => `
      <article class="watchlist-v30-card" data-watch-card="${esc(row.symbol)}">
        <button type="button" class="watchlist-v30-open" data-watch-open="${esc(row.symbol)}" data-watch-open-name="${esc(row.name)}">
          <span class="watchlist-v30-id"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)}</small></span>
          <span class="watchlist-v30-quote"><strong data-watch-price>-</strong><b class="watchlist-v30-return flat" data-watch-return>-</b></span>
          <small class="watchlist-v30-meta">1개월 수익률 · 시세 불러오는 중</small>
        </button>
        <button type="button" class="watchlist-v30-star" data-watch-remove="${esc(row.symbol)}" aria-label="${esc(row.name)} 관심종목 해제">★</button>
      </article>`).join('');
    grid.querySelectorAll('[data-watch-open]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.watchOpen, button.dataset.watchOpenName)));
    grid.querySelectorAll('[data-watch-remove]').forEach((button) => button.addEventListener('click', () => toggleWatchlist(button.dataset.watchRemove)));
    renderRecents();
    loadQuotes();
  }

  async function loadQuotes() {
    const seq = ++quoteSeq;
    const rows = [...watchlist];
    for (let i = 0; i < rows.length; i += 6) {
      const chunk = rows.slice(i, i + 6);
      try {
        const response = await fetch(`/api/compare?tickers=${encodeURIComponent(chunk.map((x) => x.symbol).join(','))}&period=1mo`, { cache: 'no-store' });
        if (!response.ok) continue;
        const data = await response.json();
        if (seq !== quoteSeq) return;
        (data.stocks || []).forEach((stock) => {
          const card = document.querySelector(`[data-watch-card="${CSS.escape(stock.ticker)}"]`);
          if (!card) return;
          const price = card.querySelector('[data-watch-price]');
          const ret = card.querySelector('[data-watch-return]');
          const meta = card.querySelector('.watchlist-v30-meta');
          if (price) price.textContent = formatPrice(stock.ticker, stock.price);
          if (ret) {
            ret.textContent = returnText(stock.return);
            ret.className = `watchlist-v30-return ${returnClass(stock.return)}`;
          }
          if (meta) meta.textContent = '1개월 수익률 · Yahoo Finance';
        });
      } catch (_) { }
    }
  }

  function openAnalysis(symbol, name) {
    recordRecent(symbol, name);
    if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
    else if (typeof window.switchTab === 'function') window.switchTab('chart');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function enhanceTickerStars() {
    const tags = Array.from(document.querySelectorAll('#ticker-tags .ticker-tag'));
    let selected = [];
    try { if (typeof selectedTickers !== 'undefined') selected = [...selectedTickers]; } catch (_) { }
    tags.forEach((tag, index) => {
      const symbol = selected[index];
      if (!symbol) return;
      let button = tag.querySelector('.tag-watchlist');
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'tag-watchlist';
        const remove = tag.querySelector('.tag-remove');
        if (remove) tag.insertBefore(button, remove); else tag.appendChild(button);
        button.addEventListener('click', (event) => {
          event.preventDefault(); event.stopPropagation();
          toggleWatchlist(button.dataset.watchSymbol, knownName(button.dataset.watchSymbol));
        });
      }
      button.dataset.watchSymbol = symbol;
      const active = isWatchlisted(symbol);
      button.classList.toggle('active', active);
      button.textContent = active ? '★' : '☆';
      button.setAttribute('aria-label', `${knownName(symbol)} ${active ? '관심종목 해제' : '관심종목 추가'}`);
    });
  }

  function wrapAnalysisState() {
    if (window.__watchlistAnalysisWrapped) return;
    window.__watchlistAnalysisWrapped = true;

    if (typeof window.addTickerDirect === 'function') {
      const base = window.addTickerDirect;
      window.addTickerDirect = function (ticker) {
        const result = base.apply(this, arguments);
        persistSelection();
        recordRecent(String(ticker || '').toUpperCase(), knownName(String(ticker || '').toUpperCase()));
        setTimeout(enhanceTickerStars, 0);
        return result;
      };
    }
    if (typeof window.removeTicker === 'function') {
      const base = window.removeTicker;
      window.removeTicker = function () {
        const result = base.apply(this, arguments);
        persistSelection();
        setTimeout(enhanceTickerStars, 0);
        return result;
      };
    }
    if (typeof window.addGlobalTicker === 'function') {
      const base = window.addGlobalTicker;
      window.addGlobalTicker = function (ticker, name) {
        try {
          if (name && typeof tickerNameMap !== 'undefined') tickerNameMap[ticker] = name;
          if (name && typeof perTickerNameMap !== 'undefined') perTickerNameMap[ticker] = name;
        } catch (_) { }
        const result = base.apply(this, arguments);
        persistSelection();
        recordRecent(String(ticker || '').toUpperCase(), name || knownName(String(ticker || '').toUpperCase()));
        return result;
      };
    }
    if (typeof window.selectSearchResult === 'function') {
      const base = window.selectSearchResult;
      window.selectSearchResult = function (symbol, name) {
        const result = base.apply(this, arguments);
        persistSelection();
        recordRecent(symbol, name);
        return result;
      };
    }
    if (typeof window.updateTags === 'function') {
      const base = window.updateTags;
      window.updateTags = function () {
        const result = base.apply(this, arguments);
        enhanceTickerStars();
        return result;
      };
    }
  }

  restoreSelection();
  wrapAnalysisState();

  window.__installWatchlist = installTab;
  window.__renderWatchlist = render;
  window.__isWatchlisted = isWatchlisted;
  window.__toggleWatchlist = toggleWatchlist;
  window.__recordRecentTicker = recordRecent;
  window.__renderHomeWatchlist = renderHomeShortcut;

  function init() {
    // Make the in-memory defaults and persisted state identical from first launch.
    saveWatchlist();
    saveRecents();
    installTab();
    wrapAnalysisState();
    try {
      if (typeof window.updateTags === 'function') window.updateTags();
      if (typeof window.loadData === 'function') window.loadData();
    } catch (_) { }
    render();
    setTimeout(renderHomeShortcut, 500);
    setTimeout(renderHomeShortcut, 1800);
    document.addEventListener('chartview:watchlist-change', renderHomeShortcut);
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(renderHomeShortcut, 250);
      const symbolNode = event.target.closest('[data-home-symbol], .screen-add[data-symbol], .screen-idea[data-symbol]');
      if (!symbolNode) return;
      const symbol = symbolNode.dataset.homeSymbol || symbolNode.dataset.symbol;
      const name = symbolNode.dataset.homeName || symbolNode.dataset.name;
      if (symbol) recordRecent(symbol, name);
    }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
