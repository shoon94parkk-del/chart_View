(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const RECENTS_KEY = 'chartview-recents-v1';
  const SELECTED_KEY = 'chartview-selected-tickers-v1';
  const NAME_KEY = 'chartview-ticker-names-v1';
  const QUOTE_CACHE_KEY = 'chartview-watchlist-quotes-v33';
  const SORT_KEY = 'chartview-watchlist-sort-v33';
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
      const parsed = raw ? JSON.parse(raw) : fallback;
      if (Array.isArray(fallback) && !Array.isArray(parsed)) return fallback;
      return parsed;
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
  let sortMode = safeParse(SORT_KEY, 'default');
  let quoteSeq = 0;
  let searchTimer = null;
  let quoteCache = safeParse(QUOTE_CACHE_KEY, { updatedAt: 0, quotes: {} });
  if (!quoteCache || typeof quoteCache !== 'object') quoteCache = { updatedAt: 0, quotes: {} };
  if (!quoteCache.quotes || typeof quoteCache.quotes !== 'object') quoteCache.quotes = {};

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

  function saveQuoteCache() {
    try { localStorage.setItem(QUOTE_CACHE_KEY, JSON.stringify(quoteCache)); } catch (_) { }
  }

  function saveSortMode() {
    try { localStorage.setItem(SORT_KEY, JSON.stringify(sortMode)); } catch (_) { }
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
    if (value == null || value === '') return '-';
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
    if (value == null || value === '') return '-';
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  }

  function marketLabel(symbol) {
    return /\.(KS|KQ)$/.test(symbol) ? 'KR' : 'US';
  }

  function quoteFor(symbol) {
    const row = quoteCache.quotes?.[symbol];
    return row && typeof row === 'object' ? row : null;
  }

  function sortRows(rows) {
    const copy = [...rows];
    if (sortMode === 'return-desc') {
      return copy.sort((a, b) => (quoteFor(b.symbol)?.return ?? -Infinity) - (quoteFor(a.symbol)?.return ?? -Infinity));
    }
    if (sortMode === 'return-asc') {
      return copy.sort((a, b) => (quoteFor(a.symbol)?.return ?? Infinity) - (quoteFor(b.symbol)?.return ?? Infinity));
    }
    if (sortMode === 'name') return copy.sort((a, b) => a.name.localeCompare(b.name, 'ko-KR'));
    return copy;
  }

  function timeLabel(timestamp) {
    const ts = Number(timestamp);
    if (!Number.isFinite(ts) || ts <= 0) return '';
    try {
      return new Date(ts).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch (_) { return ''; }
  }

  function updateUpdatedLabel(isFresh = false) {
    const node = document.querySelector('[data-watch-updated]');
    if (!node) return;
    const label = timeLabel(quoteCache.updatedAt);
    node.textContent = label ? `${label} ${isFresh ? '갱신' : '캐시'}` : '시세 준비 중';
    node.classList.toggle('fresh', Boolean(isFresh));
  }

  function updateSummary() {
    const total = document.querySelector('[data-watch-summary-total]');
    const up = document.querySelector('[data-watch-summary-up]');
    const down = document.querySelector('[data-watch-summary-down]');
    if (total) total.textContent = String(watchlist.length);
    const values = watchlist.map((row) => quoteFor(row.symbol)?.return).filter(value => value != null && value !== '').map(Number).filter(Number.isFinite);
    if (up) up.textContent = values.length ? String(values.filter((x) => x > 0).length) : '-';
    if (down) down.textContent = values.length ? String(values.filter((x) => x < 0).length) : '-';
  }

  function quoteMarkup(row) {
    const quote = quoteFor(row.symbol);
    const price = formatPrice(row.symbol, quote?.price);
    const ret = returnText(quote?.return);
    const cls = returnClass(quote?.return);
    return { price, ret, cls };
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
        <div><span>MY STOCKS · 1달 수익률</span><h3>내 관심종목</h3></div>
        <button type="button" data-home-watch-all>전체보기 →</button>
      </div>
      ${visible.length ? `<div class="home-watchlist-v30-chips">${visible.map((row) => {
        const q = quoteMarkup(row);
        return `<button type="button" data-home-watch-open="${esc(row.symbol)}" data-home-watch-name="${esc(row.name)}">
          <span class="home-watch-v33-top"><strong>${esc(row.name)}</strong><i>${marketLabel(row.symbol)}</i></span>
          <small>${esc(row.symbol)}</small>
          <span class="home-watch-v33-quote"><b data-home-watch-price>${q.price}</b><em class="${q.cls}" data-home-watch-return>${q.ret}</em></span>
        </button>`;
      }).join('')}</div>` : '<div class="home-watchlist-v30-empty"><strong>관심종목을 추가해 보세요</strong><span>가격과 1달 수익률을 홈에서 바로 확인할 수 있습니다.</span></div>'}`;
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
    tab.className = 'tab-content watchlist-tab-v30 watchlist-tab-v33';
    anchor.insertAdjacentElement('beforebegin', tab);
    tab.innerHTML = `
      <main class="watchlist-v30 watchlist-v33">
        <header class="watchlist-v30-head watchlist-v33-head">
          <div><span class="watchlist-v30-eyebrow">MY STOCKS</span><h2>관심종목</h2><p>저장한 종목의 현재가와 1달 수익률을 빠르게 확인합니다.</p></div>
          <div class="watchlist-v33-head-meta"><span class="watchlist-v30-count" data-watch-count>0개</span><small data-watch-updated>시세 준비 중</small></div>
        </header>
        <section class="watchlist-v33-summary" aria-label="관심종목 요약 · 1달 수익률 기준">
          <div><span>전체</span><strong data-watch-summary-total>0</strong></div>
          <div class="up"><span>1달 상승</span><strong data-watch-summary-up>-</strong></div>
          <div class="down"><span>1달 하락</span><strong data-watch-summary-down>-</strong></div>
        </section>
        <section class="watchlist-v30-searchbox watchlist-v33-searchbox">
          <div class="watchlist-v30-searchrow"><input id="watchlist-v30-search" type="search" placeholder="종목명 · 6자리 코드 · 해외 티커 추가" autocomplete="off" aria-label="관심종목 추가 검색"></div>
          <div id="watchlist-v30-search-results" class="watchlist-v30-search-results"></div>
        </section>
        <section class="watchlist-v30-section watchlist-v33-main-section">
          <div class="watchlist-v30-section-head watchlist-v33-section-head"><h3>내 관심종목</h3><small>카드를 누르면 종목분석</small></div>
          <div class="watchlist-v33-toolbar">
            <div class="watchlist-v33-sort" role="group" aria-label="관심종목 정렬">
              <button type="button" data-watch-sort="default">등록순</button>
              <button type="button" data-watch-sort="return-desc">1달 수익률↑</button>
              <button type="button" data-watch-sort="return-asc">1달 수익률↓</button>
              <button type="button" data-watch-sort="name">이름순</button>
            </div>
            <button type="button" class="watchlist-v33-refresh" data-watch-refresh aria-label="관심종목 시세 새로고침">↻ 새로고침</button>
          </div>
          <div id="watchlist-v30-grid" class="watchlist-v30-grid watchlist-v33-grid"></div>
        </section>
        <section class="watchlist-v30-section watchlist-v33-recent-section">
          <div class="watchlist-v30-section-head"><h3>최근 본 종목</h3><small>최대 8개</small></div>
          <div id="watchlist-v30-recents" class="watchlist-v30-recents"></div>
        </section>
        <p class="watchlist-v30-footer-note">관심종목은 이 기기에 저장됩니다. 가격은 Yahoo Finance 공개 데이터를 기준으로 표시됩니다.</p>
      </main>`;
    bindSearch(tab);
    tab.querySelectorAll('[data-watch-sort]').forEach((button) => button.addEventListener('click', () => {
      sortMode = button.dataset.watchSort || 'default';
      saveSortMode();
      renderGrid();
    }));
    tab.querySelector('[data-watch-refresh]')?.addEventListener('click', () => loadQuotes(true));
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
      const saved = isWatchlisted(row.symbol);
      return `<button type="button" class="watchlist-v30-search-item ${saved ? 'saved' : ''}" data-watch-search-symbol="${symbol}" data-watch-search-name="${name}" data-watch-search-saved="${saved ? '1' : '0'}"><span><strong>${name}</strong><small>${esc(row.market ? `${row.code || row.symbol} · ${row.market}` : row.symbol)}</small></span><b>${saved ? '저장됨 · 보기' : '+ 추가'}</b></button>`;
    }).join('');
    box.classList.add('show');
    box.querySelectorAll('[data-watch-search-symbol]').forEach((button) => button.addEventListener('click', () => {
      if (button.dataset.watchSearchSaved === '1') openAnalysis(button.dataset.watchSearchSymbol, button.dataset.watchSearchName);
      else toggleWatchlist(button.dataset.watchSearchSymbol, button.dataset.watchSearchName);
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
      }, 160);
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

  function renderGrid() {
    const grid = document.getElementById('watchlist-v30-grid');
    if (!grid) return;
    document.querySelectorAll('[data-watch-sort]').forEach((button) => button.classList.toggle('active', button.dataset.watchSort === sortMode));
    if (!watchlist.length) {
      grid.innerHTML = '<div class="watchlist-v30-empty watchlist-v33-empty"><span>☆</span><strong>관심종목이 비어 있습니다.</strong><p>종목을 저장하면 가격과 1달 수익률을 한 화면에서 비교할 수 있어요.</p><button type="button" data-watch-empty-focus>종목 추가하기</button></div>';
      grid.querySelector('[data-watch-empty-focus]')?.addEventListener('click', () => {
        const input = document.getElementById('watchlist-v30-search');
        input?.focus();
        input?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      updateSummary();
      return;
    }
    const rows = sortRows(watchlist);
    grid.innerHTML = rows.map((row) => {
      const q = quoteMarkup(row);
      return `
      <article class="watchlist-v30-card watchlist-v33-card" data-watch-card="${esc(row.symbol)}">
        <button type="button" class="watchlist-v30-open watchlist-v33-open" data-watch-open="${esc(row.symbol)}" data-watch-open-name="${esc(row.name)}" aria-label="${esc(row.name)} 종목분석 열기">
          <span class="watchlist-v33-card-top">
            <span class="watchlist-v30-id"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)}</small></span>
            <i class="watchlist-v33-market">${marketLabel(row.symbol)}</i>
          </span>
          <span class="watchlist-v30-quote"><strong data-watch-price>${q.price}</strong><b class="watchlist-v30-return ${q.cls}" data-watch-return>${q.ret}</b></span>
          <small class="watchlist-v30-meta">1달 수익률 · ${quoteFor(row.symbol) ? '저장된 시세' : '시세 불러오는 중'}</small>
          <span class="watchlist-v33-analysis-link">종목분석 <b>›</b></span>
        </button>
        <button type="button" class="watchlist-v30-star" data-watch-remove="${esc(row.symbol)}" aria-label="${esc(row.name)} 관심종목 해제">★</button>
      </article>`;
    }).join('');
    grid.querySelectorAll('[data-watch-open]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.watchOpen, button.dataset.watchOpenName)));
    grid.querySelectorAll('[data-watch-remove]').forEach((button) => button.addEventListener('click', () => toggleWatchlist(button.dataset.watchRemove)));
    updateSummary();
  }

  function render() {
    const tab = installTab();
    if (!tab) return;
    const count = tab.querySelector('[data-watch-count]');
    if (count) count.textContent = `${watchlist.length}개`;
    renderGrid();
    renderRecents();
    updateUpdatedLabel(false);
    loadQuotes(false);
  }

  function applyQuote(symbol, quote, fresh = false) {
    const card = document.querySelector(`[data-watch-card="${CSS.escape(symbol)}"]`);
    if (card) {
      const price = card.querySelector('[data-watch-price]');
      const ret = card.querySelector('[data-watch-return]');
      const meta = card.querySelector('.watchlist-v30-meta');
      if (price) price.textContent = formatPrice(symbol, quote?.price);
      if (ret) {
        ret.textContent = returnText(quote?.return);
        ret.className = `watchlist-v30-return ${returnClass(quote?.return)}`;
      }
      if (meta) meta.textContent = `1달 수익률 · ${fresh ? '방금 갱신' : '저장된 시세'}`;
    }
    const home = document.querySelector(`[data-home-watch-open="${CSS.escape(symbol)}"]`);
    if (home) {
      const price = home.querySelector('[data-home-watch-price]');
      const ret = home.querySelector('[data-home-watch-return]');
      if (price) price.textContent = formatPrice(symbol, quote?.price);
      if (ret) {
        ret.textContent = returnText(quote?.return);
        ret.className = returnClass(quote?.return);
      }
    }
  }

  async function loadQuotes(force = false) {
    const seq = ++quoteSeq;
    const rows = [...watchlist];
    const refresh = document.querySelector('[data-watch-refresh]');
    if (refresh) {
      refresh.classList.add('loading');
      refresh.disabled = true;
      refresh.textContent = '↻ 갱신 중';
    }

    rows.forEach((row) => {
      const cached = quoteFor(row.symbol);
      if (cached) applyQuote(row.symbol, cached, false);
    });
    updateSummary();
    updateUpdatedLabel(false);

    if (!rows.length) {
      if (refresh) { refresh.classList.remove('loading'); refresh.disabled = false; refresh.textContent = '↻ 새로고침'; }
      return;
    }

    const chunks = [];
    let received = 0;
    for (let i = 0; i < rows.length; i += 6) chunks.push(rows.slice(i, i + 6));
    await Promise.allSettled(chunks.map(async (chunk) => {
      const response = await fetch(`/api/compare?tickers=${encodeURIComponent(chunk.map((x) => x.symbol).join(','))}&period=1mo${force ? `&refresh=${Date.now()}` : ''}`, { cache: 'no-store' });
      if (!response.ok) return;
      const data = await response.json();
      if (seq !== quoteSeq) return;
      (data.stocks || []).forEach((stock) => {
        const symbol = String(stock.ticker || '').toUpperCase();
        if (!symbol) return;
        const quote = { price: stock.price == null ? null : Number(stock.price), return: stock.return == null ? null : Number(stock.return), updatedAt: Date.now() };
        received += 1;
        quoteCache.quotes[symbol] = quote;
        applyQuote(symbol, quote, true);
      });
    }));

    if (seq !== quoteSeq) return;
    if (received === rows.length) quoteCache.updatedAt = Date.now();
    saveQuoteCache();
    updateSummary();
    updateUpdatedLabel(received === rows.length);
    if (received < rows.length) {
      const label = document.querySelector('[data-watch-updated]');
      if (label) label.textContent = received ? '일부 시세 갱신 지연 · 이전값 유지' : '갱신 실패 · 이전값 유지';
    }
    if (sortMode === 'return-desc' || sortMode === 'return-asc') renderGrid();
    renderHomeShortcut();
    if (refresh) {
      refresh.classList.remove('loading');
      refresh.disabled = false;
      refresh.textContent = '↻ 새로고침';
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
    saveWatchlist();
    saveRecents();
    installTab();
    wrapAnalysisState();
    try {
      if (typeof window.updateTags === 'function') window.updateTags();
      if (typeof window.loadData === 'function') window.loadData();
    } catch (_) { }
    renderHomeShortcut();
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
