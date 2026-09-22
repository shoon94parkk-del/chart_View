(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const RECENTS_KEY = 'chartview-recents-v1';
  const SELECTED_KEY = 'chartview-selected-tickers-v1';
  const NAME_KEY = 'chartview-ticker-names-v1';
  const QUOTE_CACHE_KEY = 'chartview-watchlist-quotes-v33';
  const SORT_KEY = 'chartview-watchlist-sort-v33';
  const QUOTE_FRESH_MS = 5 * 60 * 1000;
  const RETURN_FRESH_MS = 12 * 60 * 60 * 1000;
  const ENTRY_REFRESH_THROTTLE_MS = 60 * 1000;
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
  let quoteLoadPromise = null;
  let searchTimer = null;
  let lastEntryRefreshAt = 0;
  let entryReturnTimer = null;
  const quoteQueue = new Set();
  const returnQueue = new Set();
  const quoteStatus = new Map();
  let quoteCache = safeParse(QUOTE_CACHE_KEY, { updatedAt: 0, quotes: {} });
  if (!quoteCache || typeof quoteCache !== 'object') quoteCache = { updatedAt: 0, quotes: {} };
  if (!quoteCache.quotes || typeof quoteCache.quotes !== 'object') quoteCache.quotes = {};
  Object.values(quoteCache.quotes).forEach((quote) => {
    if (!quote || typeof quote !== 'object') return;
    if (quote.return !== null && quote.return !== undefined && !quote.returnUpdatedAt) {
      quote.returnUpdatedAt = Number(quote.updatedAt || quoteCache.updatedAt || 0);
    }
    if (typeof quote.receivedAt === 'string'
      && quote.receivedAt
      && !/(?:Z|[+-]\d{2}:\d{2})$/.test(quote.receivedAt)
      && !/^\d{10,13}$/.test(quote.receivedAt.trim())) {
      quote.receivedAt = '';
    }
  });

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
      if (Array.isArray(saved)) {
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
    const added = index < 0;
    if (!added) watchlist.splice(index, 1);
    else {
      if (watchlist.length >= MAX_WATCHLIST) {
        alert(`관심종목은 최대 ${MAX_WATCHLIST}개까지 저장할 수 있어요.`);
        return false;
      }
      watchlist.unshift(row);
    }
    saveWatchlist();
    document.dispatchEvent(new CustomEvent('chartview:watchlist-change'));
    // Persist and paint immediately. Adding/removing one stock must not block on
    // refreshing every existing watchlist quote and 1-month return.
    render({ refreshQuotes: false });
    renderHomeShortcut();
    enhanceTickerStars();
    if (added) {
      setTimeout(() => hydrateAddedWatchlistRow(row), 0);
    }
    return added;
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

  function normalizeDateValue(value) {
    if (value === null || value === undefined || value === '') return null;
    const raw = String(value).trim();
    let date;
    if (typeof value === 'number' || /^\d{10,13}$/.test(raw)) {
      const numeric = Number(raw);
      if (!Number.isFinite(numeric)) return null;
      date = new Date(numeric < 1e12 ? numeric * 1000 : numeric);
    } else {
      date = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(`${raw}T00:00:00Z`) : new Date(raw);
    }
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function timeLabel(value) {
    const date = normalizeDateValue(value);
    if (!date) return '';
    try {
      return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
    } catch (_) { return ''; }
  }

  function updateUpdatedLabel(isFresh = false) {
    const node = document.querySelector('[data-watch-updated]');
    if (!node) return;
    const label = timeLabel(quoteCache.updatedAt);
    node.textContent = label ? `${label} KST 조회${isFresh ? '' : ' · 저장 시세'}` : '시세 준비 중';
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

  function tradeDateLabel(value) {
    const date = normalizeDateValue(value);
    if (!date) return '기준일 미확인';
    return `${String(date.getUTCMonth() + 1).padStart(2, '0')}.${String(date.getUTCDate()).padStart(2, '0')} 종가`;
  }

  function quoteMetaText(quote, fresh = false, symbol = '') {
    const state = symbol ? quoteStatus.get(symbol) : '';
    if (!quote) {
      if (state === 'error') return '조회 실패 · 다시 시도';
      if (state === 'partial') return '가격 조회됨 · 1달 수익률 조회 실패';
      return '시세 불러오는 중';
    }
    const received = timeLabel(quote.receivedAt || quote.quoteAsOf || quote.updatedAt);
    const parts = [
      quote.return == null ? '1달 수익률 확인 중' : '1달 수익률',
      quote.tradeDate ? tradeDateLabel(quote.tradeDate) : '',
      received ? `${received} KST 조회` : '',
    ].filter(Boolean);
    if (state === 'error') parts.push('이전값');
    else if (state === 'partial') parts.push(quote.return == null ? '수익률 조회 실패' : '이전 수익률');
    return parts.join(' · ');
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
      const summaryCard = body.querySelector('.home16-summary-card');
      if (summaryCard) summaryCard.insertAdjacentElement('afterend', section);
      else body.prepend(section);
    }
    const visible = watchlist.slice(0, 4);
    section.innerHTML = `
      <div class="home-block-head home-watchlist-v30-head">
        <div><span>관심종목 · 1달 수익률</span><h3>내 관심종목</h3></div>
        <button type="button" data-home-watch-all>전체보기 →</button>
      </div>
      ${visible.length ? `<div class="home-watchlist-v30-chips">${visible.map((row) => {
        const q = quoteMarkup(row);
        return `<button type="button" data-home-watch-open="${esc(row.symbol)}" data-home-watch-name="${esc(row.name)}" aria-label="${esc(row.name)} 상세 보기">
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
        <div class="watchlist-v34-status" data-watch-status role="status" aria-live="polite" hidden>
          <span data-watch-status-text></span>
          <button type="button" data-watch-retry hidden>실패 종목 재시도</button>
        </div>
        <section class="watchlist-v30-searchbox watchlist-v33-searchbox">
          <div class="watchlist-v30-searchrow"><input id="watchlist-v30-search" type="search" placeholder="종목명 · 6자리 코드 · 해외 티커 추가" autocomplete="off" aria-label="관심종목 추가 검색"></div>
          <div id="watchlist-v30-search-results" class="watchlist-v30-search-results"></div>
        </section>
        <section class="watchlist-v30-section watchlist-v33-main-section">
          <div class="watchlist-v30-section-head watchlist-v33-section-head"><h3>종목 목록</h3><small>카드를 누르면 종목 상세</small></div>
          <div class="watchlist-v33-toolbar">
            <select class="watchlist-mobile-sort" aria-label="관심종목 정렬 선택">
              <option value="default">등록순</option><option value="return-desc">수익률 높은순</option>
              <option value="return-asc">수익률 낮은순</option><option value="name">이름순</option>
            </select>
            <div class="watchlist-v33-sort" role="group" aria-label="관심종목 정렬">
              <button type="button" data-watch-sort="default">등록순</button>
              <button type="button" data-watch-sort="return-desc">수익률 높은순</button>
              <button type="button" data-watch-sort="return-asc">수익률 낮은순</button>
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
        <p class="watchlist-v30-footer-note">관심종목은 이 기기에 저장됩니다. 카드의 거래 기준일과 조회 시각을 함께 확인하세요. 실제 출처를 확인할 수 없는 시세는 출처 미확인으로 취급합니다.</p>
      </main>`;
    bindSearch(tab);
    tab.querySelectorAll('[data-watch-sort]').forEach((button) => button.addEventListener('click', () => {
      sortMode = button.dataset.watchSort || 'default';
      saveSortMode();
      renderGrid();
    }));
    tab.querySelector('.watchlist-mobile-sort').addEventListener('change', (event) => {
      sortMode = event.target.value;
      saveSortMode();
      renderGrid();
    });
    tab.querySelector('[data-watch-refresh]')?.addEventListener('click', () => loadQuotes(true));
    tab.querySelector('[data-watch-retry]')?.addEventListener('click', retryFailedQuotes);
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
    const mobileSort = document.querySelector('.watchlist-mobile-sort');
    if (mobileSort) mobileSort.value = sortMode;
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
        <button type="button" class="watchlist-v30-open watchlist-v33-open" data-watch-open="${esc(row.symbol)}" data-watch-open-name="${esc(row.name)}" aria-label="${esc(row.name)} 종목 상세 열기">
          <span class="watchlist-v33-card-top">
            <span class="watchlist-v30-id"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)}</small></span>
            <i class="watchlist-v33-market">${marketLabel(row.symbol)}</i>
          </span>
          <span class="watchlist-v30-quote"><strong data-watch-price>${q.price}</strong><b class="watchlist-v30-return ${q.cls}" data-watch-return>${q.ret}</b></span>
          <small class="watchlist-v30-meta">${esc(quoteMetaText(quoteFor(row.symbol), false, row.symbol))}</small>
          <span class="watchlist-v33-analysis-link">상세 보기 <b>›</b></span>
        </button>
        <button type="button" class="watchlist-v30-star" data-watch-remove="${esc(row.symbol)}" aria-label="${esc(row.name)} 관심종목 해제">★</button>
      </article>`;
    }).join('');
    grid.querySelectorAll('[data-watch-open]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.watchOpen, button.dataset.watchOpenName)));
    grid.querySelectorAll('[data-watch-remove]').forEach((button) => button.addEventListener('click', () => toggleWatchlist(button.dataset.watchRemove)));
    updateSummary();
  }

  function render({ refreshQuotes = false } = {}) {
    const tab = installTab();
    if (!tab) return;
    const count = tab.querySelector('[data-watch-count]');
    if (count) count.textContent = `${watchlist.length}개`;
    renderGrid();
    renderRecents();
    updateUpdatedLabel(false);
    if (refreshQuotes) loadQuotes(false);
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
      if (meta) meta.textContent = quoteMetaText(quote, fresh, symbol);
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

  function quoteIsFresh(symbol) {
    const quote = quoteFor(symbol);
    return Boolean(quote) && Date.now() - Number(quote.updatedAt || 0) < QUOTE_FRESH_MS;
  }

  function returnIsFresh(symbol) {
    const quote = quoteFor(symbol);
    return Boolean(quote)
      && quote.return !== null && quote.return !== undefined
      && Date.now() - Number(quote.returnUpdatedAt || 0) < RETURN_FRESH_MS;
  }

  function setRowState(symbol, state) {
    if (!symbol) return;
    quoteStatus.set(symbol, state);
    const quote = quoteFor(symbol);
    applyQuote(symbol, quote, state === 'fresh');
  }

  function updateWatchStatus() {
    const root = document.querySelector('[data-watch-status]');
    const text = document.querySelector('[data-watch-status-text]');
    const retry = document.querySelector('[data-watch-retry]');
    if (!root || !text || !retry) return;
    const symbols = watchlist.map((row) => row.symbol);
    const loading = symbols.filter((symbol) => quoteStatus.get(symbol) === 'loading');
    const failed = symbols.filter((symbol) => ['error', 'partial'].includes(quoteStatus.get(symbol)));
    if (loading.length) {
      root.hidden = false;
      root.dataset.state = 'loading';
      text.textContent = `시세 갱신 중 · ${loading.length}개`;
      retry.hidden = true;
      return;
    }
    if (failed.length) {
      root.hidden = false;
      root.dataset.state = 'error';
      text.textContent = failed.length === symbols.length
        ? '시세를 불러오지 못했어요. 저장된 이전값이 있으면 유지합니다.'
        : `일부 시세 갱신 실패 · ${failed.length}개`;
      retry.hidden = false;
      return;
    }
    root.hidden = true;
    root.dataset.state = 'ready';
    text.textContent = '';
    retry.hidden = true;
  }

  function queueRows(rows, force = false) {
    rows.forEach((row) => {
      const symbol = row.symbol;
      const needsQuote = force || !quoteIsFresh(symbol);
      const needsReturn = force || !returnIsFresh(symbol);
      if (needsQuote) quoteQueue.add(symbol);
      if (needsReturn) returnQueue.add(symbol);
      if (needsQuote || needsReturn) quoteStatus.set(symbol, 'loading');
    });
    updateWatchStatus();
  }

  async function fetchQuoteBatch(symbols) {
    if (!symbols.length) return;
    const response = await fetch(`/api/quotes?tickers=${encodeURIComponent(symbols.join(','))}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`quotes ${response.status}`);
    const data = await response.json();
    const received = new Set();
    (data.results || []).forEach((item) => {
      const symbol = String(item.ticker || '').toUpperCase();
      if (!symbol || !isWatchlisted(symbol)) return;
      received.add(symbol);
      const previous = quoteFor(symbol) || {};
      const quote = {
        ...previous,
        price: item.price == null ? previous.price ?? null : Number(item.price),
        currency: item.currency || previous.currency || '',
        quoteAsOf: item.asOf || previous.quoteAsOf || '',
        receivedAt: data.fetchedAt || previous.receivedAt || '',
        source: item.source || data.source || previous.source || '출처 미확인',
        priceBasis: 'latest_provider_quote',
        updatedAt: Date.now(),
      };
      quoteCache.quotes[symbol] = quote;
      if (!returnQueue.has(symbol)) quoteStatus.set(symbol, 'fresh');
      applyQuote(symbol, quote, true);
    });
    symbols.forEach((symbol) => {
      if (!isWatchlisted(symbol) || received.has(symbol)) return;
      quoteStatus.set(symbol, quoteFor(symbol) ? 'error' : 'error');
      applyQuote(symbol, quoteFor(symbol), false);
    });
  }

  async function fetchReturnBatch(symbols) {
    if (!symbols.length) return;
    const response = await fetch(`/api/compare?tickers=${encodeURIComponent(symbols.join(','))}&period=1mo&refresh=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`returns ${response.status}`);
    const data = await response.json();
    const received = new Set();
    (data.stocks || []).forEach((stock) => {
      const symbol = String(stock.ticker || '').toUpperCase();
      if (!symbol || !isWatchlisted(symbol)) return;
      received.add(symbol);
      const previous = quoteFor(symbol) || {};
      const lastPoint = Array.isArray(stock.data) && stock.data.length ? stock.data[stock.data.length - 1] : null;
      const tradeDate = stock.actualEnd || stock.endDate || lastPoint?.time || '';
      const quote = {
        ...previous,
        price: previous.price == null && stock.price != null ? Number(stock.price) : previous.price ?? null,
        return: stock.return == null ? previous.return ?? null : Number(stock.return),
        tradeDate: tradeDate || previous.tradeDate || '',
        quoteAsOf: previous.quoteAsOf || stock.quoteAsOf || stock.asOf || tradeDate || '',
        receivedAt: data.fetchedAt || previous.receivedAt || '',
        source: previous.source || stock.source || data.source || '출처 미확인',
        returnSource: stock.source || data.source || '출처 미확인',
        returnBasis: stock.priceBasis || 'provider',
        returnUpdatedAt: Date.now(),
        updatedAt: Number(previous.updatedAt || Date.now()),
      };
      quoteCache.quotes[symbol] = quote;
      if (quoteStatus.get(symbol) !== 'error') quoteStatus.set(symbol, 'fresh');
      applyQuote(symbol, quote, true);
    });
    symbols.forEach((symbol) => {
      if (!isWatchlisted(symbol) || received.has(symbol)) return;
      quoteStatus.set(symbol, quoteFor(symbol) ? 'partial' : 'error');
      applyQuote(symbol, quoteFor(symbol), false);
    });
  }

  async function runQuoteQueues() {
    const refresh = document.querySelector('[data-watch-refresh]');
    if (refresh) {
      refresh.classList.add('loading');
      refresh.disabled = true;
      refresh.textContent = '↻ 갱신 중';
    }
    ++quoteSeq;
    try {
      while (quoteQueue.size || returnQueue.size) {
        if (quoteQueue.size) {
          const symbols = [...quoteQueue].slice(0, 20);
          symbols.forEach((symbol) => quoteQueue.delete(symbol));
          try {
            await fetchQuoteBatch(symbols);
          } catch (_) {
            symbols.forEach((symbol) => {
              if (!isWatchlisted(symbol)) return;
              quoteStatus.set(symbol, quoteFor(symbol) ? 'error' : 'error');
              applyQuote(symbol, quoteFor(symbol), false);
            });
          }
          updateSummary();
          updateWatchStatus();
          if (quoteQueue.size) continue;
        }

        if (returnQueue.size) {
          const symbols = [...returnQueue].slice(0, 6);
          symbols.forEach((symbol) => returnQueue.delete(symbol));
          try {
            await fetchReturnBatch(symbols);
          } catch (_) {
            symbols.forEach((symbol) => {
              if (!isWatchlisted(symbol)) return;
              quoteStatus.set(symbol, quoteFor(symbol) ? 'partial' : 'error');
              applyQuote(symbol, quoteFor(symbol), false);
            });
          }
          updateSummary();
          updateWatchStatus();
        }
      }

      const liveRows = [...watchlist];
      if (liveRows.length && liveRows.every((row) => quoteIsFresh(row.symbol))) {
        quoteCache.updatedAt = Date.now();
      }
      saveQuoteCache();
      updateSummary();
      updateUpdatedLabel(liveRows.length > 0 && liveRows.every((row) => quoteIsFresh(row.symbol)));
      updateWatchStatus();
      if (sortMode === 'return-desc' || sortMode === 'return-asc') renderGrid();
      renderHomeShortcut();
      return quoteCache;
    } finally {
      if (refresh) {
        refresh.classList.remove('loading');
        refresh.disabled = false;
        refresh.textContent = '↻ 새로고침';
      }
    }
  }

  async function hydrateAddedWatchlistRow(row) {
    if (!row || !row.symbol || !isWatchlisted(row.symbol)) return;
    const symbol = row.symbol;
    quoteStatus.set(symbol, 'loading');
    updateWatchStatus();

    // Fast path: paint current price first without waiting for 1-month history.
    try {
      const response = await fetch(`/api/quotes?tickers=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
      if (response.ok && isWatchlisted(symbol)) {
        const data = await response.json();
        const item = (data.results || []).find((quote) => String(quote.ticker || quote.symbol || '').toUpperCase() === symbol);
        if (item) {
          const previous = quoteFor(symbol) || {};
          const quote = {
            ...previous,
            price: item.price == null ? previous.price ?? null : Number(item.price),
            currency: item.currency || previous.currency || '',
            quoteAsOf: item.asOf || previous.quoteAsOf || '',
            receivedAt: data.fetchedAt || previous.receivedAt || '',
            source: item.source || data.source || previous.source || '출처 미확인',
            priceBasis: item.priceBasis || previous.priceBasis || 'latest_provider_quote',
            updatedAt: Date.now(),
          };
          quoteCache.quotes[symbol] = quote;
          saveQuoteCache();
          applyQuote(symbol, quote, true);
          updateSummary();
        }
      }
    } catch (_) { }

    if (!isWatchlisted(symbol)) return;

    // Slow path: fetch only this one stock's 1-month return in the background.
    try {
      const response = await fetch(`/api/compare?tickers=${encodeURIComponent(symbol)}&period=1mo`, { cache: 'no-store' });
      if (!response.ok || !isWatchlisted(symbol)) throw new Error(`returns ${response.status}`);
      const data = await response.json();
      const stock = (data.stocks || []).find((item) => String(item.ticker || '').toUpperCase() === symbol);
      if (!stock) throw new Error('missing return row');
      const lastPoint = Array.isArray(stock.data) && stock.data.length ? stock.data[stock.data.length - 1] : null;
      const tradeDate = stock.actualEnd || stock.endDate || lastPoint?.time || '';
      const previous = quoteFor(symbol) || {};
      const quote = {
        ...previous,
        price: previous.price == null && stock.price != null ? Number(stock.price) : previous.price ?? null,
        return: stock.return == null ? previous.return ?? null : Number(stock.return),
        tradeDate: tradeDate || previous.tradeDate || '',
        quoteAsOf: previous.quoteAsOf || stock.quoteAsOf || stock.asOf || tradeDate || '',
        receivedAt: data.fetchedAt || previous.receivedAt || '',
        source: previous.source || stock.source || data.source || '출처 미확인',
        returnSource: stock.source || data.source || '출처 미확인',
        returnBasis: stock.priceBasis || 'provider',
        returnUpdatedAt: Date.now(),
        updatedAt: Number(previous.updatedAt || Date.now()),
      };
      quoteCache.quotes[symbol] = quote;
      quoteStatus.set(symbol, 'fresh');
      saveQuoteCache();
      applyQuote(symbol, quote, true);
      updateSummary();
      updateWatchStatus();
      renderHomeShortcut();
      if (sortMode === 'return-desc' || sortMode === 'return-asc') renderGrid();
    } catch (_) {
      if (!isWatchlisted(symbol)) return;
      quoteStatus.set(symbol, quoteFor(symbol) ? 'partial' : 'error');
      applyQuote(symbol, quoteFor(symbol), false);
      updateWatchStatus();
    }
  }

  async function loadQuoteRows(rows, force = false) {
    const targets = dedupe((rows || []).filter((row) => row && isWatchlisted(row.symbol)));
    targets.forEach((row) => {
      const cached = quoteFor(row.symbol);
      if (cached) applyQuote(row.symbol, cached, false);
    });
    updateSummary();
    updateUpdatedLabel(false);
    queueRows(targets, force);

    if (!quoteQueue.size && !returnQueue.size) {
      updateWatchStatus();
      return quoteCache;
    }
    if (quoteLoadPromise) return quoteLoadPromise;

    const job = runQuoteQueues();
    quoteLoadPromise = job;
    try {
      return await job;
    } finally {
      if (quoteLoadPromise === job) quoteLoadPromise = null;
      if (quoteQueue.size || returnQueue.size) {
        const pending = watchlist.filter((row) => quoteQueue.has(row.symbol) || returnQueue.has(row.symbol));
        if (pending.length) loadQuoteRows(pending, false);
      }
    }
  }

  async function refreshCurrentQuotesQuietly() {
    const symbols = watchlist
      .map((row) => row.symbol)
      .filter((symbol) => !quoteIsFresh(symbol));
    if (!symbols.length) return;

    try {
      await fetchQuoteBatch(symbols.slice(0, 20));
      quoteCache.updatedAt = Date.now();
      saveQuoteCache();
      updateSummary();
      updateUpdatedLabel(false);
      renderHomeShortcut();
    } catch (_) {
      // Screen entry must remain instant even when the provider is slow/down.
    }
  }

  async function refreshReturnsQuietly() {
    const symbols = watchlist
      .map((row) => row.symbol)
      .filter((symbol) => !returnIsFresh(symbol));
    if (!symbols.length) return;

    for (let i = 0; i < symbols.length; i += 6) {
      const batch = symbols.slice(i, i + 6);
      try {
        await fetchReturnBatch(batch);
      } catch (_) {
        // Keep cached returns; explicit refresh owns user-visible retry state.
      }
    }
    saveQuoteCache();
    updateSummary();
    renderHomeShortcut();
    if (sortMode === 'return-desc' || sortMode === 'return-asc') renderGrid();
  }

  function refreshWatchlistOnEntry() {
    const now = Date.now();
    if (now - lastEntryRefreshAt < ENTRY_REFRESH_THROTTLE_MS) return;
    lastEntryRefreshAt = now;

    // Entry is stale-while-revalidate: paint cached rows immediately, then only
    // refresh lightweight current quotes. Historical 1-month returns are much
    // more expensive and change far less often, so refresh them later and only
    // when their separate long TTL has expired.
    refreshCurrentQuotesQuietly();

    clearTimeout(entryReturnTimer);
    const runReturns = () => refreshReturnsQuietly();
    if ('requestIdleCallback' in window) {
      entryReturnTimer = setTimeout(() => requestIdleCallback(runReturns, { timeout: 2500 }), 1200);
    } else {
      entryReturnTimer = setTimeout(runReturns, 1800);
    }
  }

  async function loadQuotes(force = false) {
    return loadQuoteRows([...watchlist], force);
  }

  function retryFailedQuotes() {
    const rows = watchlist.filter((row) => ['error', 'partial'].includes(quoteStatus.get(row.symbol)));
    if (!rows.length) return;
    queueRows(rows, true);
    if (!quoteLoadPromise) loadQuotes(false);
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
  window.__refreshWatchlistOnEntry = refreshWatchlistOnEntry;
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
      if (typeof window.loadData === 'function' && document.getElementById('chart-tab')?.classList.contains('active')) window.loadData();
    } catch (_) { }
    renderHomeShortcut();
    // App boot only paints locally cached watchlist data. Do not start a hidden
    // full watchlist quote/history refresh before the user even opens the tab.
    render({ refreshQuotes: false });
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
