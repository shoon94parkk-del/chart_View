(() => {
  'use strict';
  if (window.__chartViewMyHubV41Installed) return;
  window.__chartViewMyHubV41Installed = true;

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const PAGE_SIZE = 10;
  let activeView = 'stocks';
  let activeSymbol = 'ALL';
  let sortMode = 'latest';
  let renderedCount = PAGE_SIZE;
  let newsItems = [];
  let groups = [];
  let loadSeq = 0;
  let controller = null;
  let lastSuccessKey = '';
  const newsState = { requestedAt: 0, receivedAt: 0, lastError: null, isStale: false, partialFailures: 0, loading: false, key: '' };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function watchlistRows() {
    if (window.ChartViewState) return window.ChartViewState.getWatchlist().items.slice(0, 20);
    try {
      const rows = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || '[]');
      return Array.isArray(rows) ? rows.slice(0, 20) : [];
    } catch (_) { return []; }
  }

  function requestKey(rows) { return rows.map((row) => `${row.symbol}:${row.name || row.symbol}`).join('|'); }
  function emitState() { document.dispatchEvent(new CustomEvent('chartview:v41-news-state', { detail: { ...newsState } })); }
  function emitRendered() { document.dispatchEvent(new CustomEvent('chartview:v41-news-rendered')); }

  function category(item) {
    const title = String(item?.title || '').toLowerCase();
    if (/실적|영업이익|매출|earnings|revenue|guidance/.test(title)) return '실적';
    if (/수주|계약|공급|contract|deal|order/.test(title)) return '계약·수주';
    if (/인수|합병|acqui|merger/.test(title)) return 'M&A';
    if (/배당|자사주|buyback|dividend/.test(title)) return '주주환원';
    if (/승인|fda|규제|sec|소송|lawsuit|리콜|recall/.test(title)) return '규제·법률';
    if (/목표가|투자의견|upgrade|downgrade|forecast/.test(title)) return '시장 의견';
    return '기업 뉴스';
  }

  function relativeTime(value) {
    const ts = Date.parse(value || '');
    if (!Number.isFinite(ts)) return '';
    const min = Math.max(0, Math.floor((Date.now() - ts) / 60000));
    if (min < 60) return `${Math.max(1, min)}분 전`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h}시간 전`;
    const d = Math.floor(h / 24);
    return d < 7 ? `${d}일 전` : new Date(ts).toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' });
  }

  function normalizedScore(item) {
    const raw = Number(item?.score);
    return Number.isFinite(raw) ? raw : -Infinity;
  }

  function flatten(payload) {
    const merged = new Map();
    for (const group of Array.isArray(payload?.groups) ? payload.groups : []) {
      for (const item of Array.isArray(group?.items) ? group.items : []) {
        const key = item.url || `${item.title}|${item.publishedAt || ''}`;
        if (!key) continue;
        let row = merged.get(key);
        if (!row) {
          row = { ...item, symbol: item.symbol || group.symbol, name: item.name || group.name || item.symbol, relatedSymbols: [], relatedNames: {}, relations: {} };
          merged.set(key, row);
        }
        if (!row.relatedSymbols.includes(group.symbol)) row.relatedSymbols.push(group.symbol);
        row.relatedNames[group.symbol] = group.name || group.symbol;
        row.relations[group.symbol] = { type: item.relationType || 'related', basis: item.relationBasis || '제공처 종목 태그 기준' };
      }
    }
    if (!merged.size) {
      for (const item of Array.isArray(payload?.items) ? payload.items : []) {
        const key = item.url || `${item.title}|${item.publishedAt || ''}`;
        if (!key || merged.has(key)) continue;
        merged.set(key, { ...item, relatedSymbols: [item.symbol], relatedNames: { [item.symbol]: item.name || item.symbol }, relations: { [item.symbol]: { type: item.relationType || 'related', basis: item.relationBasis || '제공처 종목 태그 기준' } } });
      }
    }
    return [...merged.values()];
  }

  function ensureHub() {
    const tab = document.getElementById('watchlist-tab');
    const main = tab?.querySelector('.watchlist-v30');
    if (!tab || !main) return false;
    tab.dataset.myHubVersion = 'v42';
    const head = main.querySelector('.watchlist-v30-head');
    if (head) {
      const title = head.querySelector('h2');
      const intro = head.querySelector('p');
      if (title) title.textContent = '내 관심종목';
      if (intro) intro.textContent = '관심종목과 관련 뉴스를 한 화면에서 확인합니다.';
    }
    if (!main.querySelector('[data-v41-switch]')) {
      const nav = document.createElement('nav');
      nav.className = 'my-hub-v41-switch';
      nav.dataset.v41Switch = '1';
      nav.setAttribute('aria-label', '관심 허브 보기 전환');
      nav.innerHTML = `<button type="button" data-v41-view="stocks" class="active">관심종목</button><button type="button" data-v41-view="news">내 종목 뉴스</button>`;
      (head || main.firstElementChild)?.insertAdjacentElement('afterend', nav);
      nav.addEventListener('click', (event) => {
        const button = event.target.closest('[data-v41-view]');
        if (button) setView(button.dataset.v41View);
      });
    }
    if (!main.querySelector('[data-v41-news]')) {
      const news = document.createElement('section');
      news.className = 'my-hub-v41-news';
      news.dataset.v41News = '1';
      news.hidden = true;
      news.innerHTML = `
        <div class="my-hub-v41-news-head"><div><span>MY NEWS</span><h3>내 종목 뉴스</h3><p>관심종목 전체의 최신 기사를 모아봅니다.</p></div><button type="button" data-v41-refresh>↻ 새로고침</button></div>
        <div class="my-hub-v41-controls"><div class="my-hub-v41-chips" data-v41-chips></div><div class="my-hub-v41-sort" role="group" aria-label="뉴스 정렬"><button type="button" data-v41-sort="latest" class="active">최신순</button><button type="button" data-v41-sort="relevance">관련도순</button></div></div>
        <div class="my-hub-v41-status" data-v41-status role="status"></div>
        <div class="my-hub-v41-feed" data-v41-feed></div>
        <button type="button" class="my-hub-v41-more" data-v41-more hidden>뉴스 더 보기</button>`;
      main.appendChild(news);
      news.querySelector('[data-v41-refresh]').addEventListener('click', () => loadNews(true));
      news.querySelector('[data-v41-more]').addEventListener('click', () => { renderedCount += PAGE_SIZE; renderFeed(); });
      news.querySelector('[data-v41-sort="latest"]').addEventListener('click', () => { sortMode = 'latest'; renderedCount = PAGE_SIZE; renderFeed(); });
      news.querySelector('[data-v41-sort="relevance"]').addEventListener('click', () => { sortMode = 'relevance'; renderedCount = PAGE_SIZE; renderFeed(); });
      news.addEventListener('click', (event) => {
        const button = event.target.closest('[data-v41-detail]');
        if (!button) return;
        window.__openStockDetail?.(button.dataset.v41Detail, button.dataset.v41Name);
      });
    }
    applyView();
    return true;
  }

  function stockSections() {
    const main = document.querySelector('#watchlist-tab .watchlist-v30');
    if (!main) return [];
    return [...main.children].filter((node) => !node.matches('.watchlist-v30-head,.my-hub-v41-switch,.my-hub-v41-news'));
  }

  function applyView() {
    const tab = document.getElementById('watchlist-tab');
    if (!tab) return;
    tab.querySelectorAll('[data-v41-view]').forEach((b) => {
      const on = b.dataset.v41View === activeView;
      b.classList.toggle('active', on); b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const news = tab.querySelector('[data-v41-news]');
    stockSections().forEach((node) => { node.hidden = activeView === 'news'; });
    if (news) news.hidden = activeView !== 'news';
  }

  function setView(view, options = {}) {
    activeView = view === 'news' ? 'news' : 'stocks';
    ensureHub(); applyView();
    if (activeView === 'news') {
      loadNews(false);
      if (options.scroll !== false) document.querySelector('[data-v41-news]')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }

  function ensureActiveSymbol(rows) {
    if (activeSymbol !== 'ALL' && !rows.some((row) => row.symbol === activeSymbol)) activeSymbol = 'ALL';
  }

  function renderChips(rows) {
    ensureActiveSymbol(rows);
    const root = document.querySelector('[data-v41-chips]');
    if (!root) return;
    root.innerHTML = [`<button type="button" data-v41-symbol="ALL" class="${activeSymbol === 'ALL' ? 'active' : ''}">전체</button>`, ...rows.map((row) => `<button type="button" data-v41-symbol="${esc(row.symbol)}" class="${activeSymbol === row.symbol ? 'active' : ''}">${esc(row.name || row.symbol)}</button>`)].join('');
    root.querySelectorAll('[data-v41-symbol]').forEach((button) => button.addEventListener('click', () => {
      activeSymbol = button.dataset.v41Symbol || 'ALL'; renderedCount = PAGE_SIZE; renderChips(rows); renderFeed();
    }));
  }

  function relationFor(item, targetSymbol) {
    const symbol = targetSymbol && targetSymbol !== 'ALL' ? targetSymbol : item.symbol;
    const meta = item.relations?.[symbol] || { type: item.relationType || 'related', basis: item.relationBasis || '제공처 종목 태그 기준' };
    const shared = (item.relatedSymbols || []).length > 1;
    return { label: meta.type === 'direct' ? (shared ? '직접·공동 관련' : '직접 관련') : (shared ? '공동·연관' : '업종·연관'), basis: meta.basis };
  }

  function detailTarget(item) {
    const rows = watchlistRows();
    const symbol = activeSymbol !== 'ALL' && (item.relatedSymbols || []).includes(activeSymbol) ? activeSymbol : item.symbol;
    const row = rows.find((r) => r.symbol === symbol);
    return { symbol, name: row?.name || item.relatedNames?.[symbol] || item.name || symbol };
  }

  function renderStatus(total, visible) {
    const status = document.querySelector('[data-v41-status]');
    if (!status) return;
    status.dataset.stale = newsState.isStale ? 'true' : 'false';
    if (newsState.loading) {
      status.innerHTML = `<strong>새 뉴스를 불러오는 중…</strong>${newsItems.length ? '<span>기존 뉴스는 그대로 유지합니다.</span>' : ''}`;
      return;
    }
    if (newsState.lastError) {
      status.innerHTML = newsItems.length
        ? `<strong>새 뉴스 갱신에 실패했습니다.</strong> <span>이전 수신 데이터 ${visible}/${total}건을 표시합니다.</span>`
        : '<strong>뉴스를 불러오지 못했습니다.</strong> <span>연결 후 새로고침해 주세요.</span>';
      return;
    }
    if (!total) {
      status.textContent = '표시할 뉴스가 없습니다.';
      return;
    }
    status.textContent = `${total}건 중 ${visible}건 표시${newsState.partialFailures ? ` · ${newsState.partialFailures}개 종목 부분 실패` : ''}`;
  }

  function renderFeed() {
    const root = document.querySelector('[data-v41-feed]');
    const more = document.querySelector('[data-v41-more]');
    if (!root) return;
    document.querySelectorAll('[data-v41-sort]').forEach((b) => b.classList.toggle('active', b.dataset.v41Sort === sortMode));
    let rows = newsItems.filter((item) => activeSymbol === 'ALL' || (item.relatedSymbols || [item.symbol]).includes(activeSymbol));
    rows = [...rows].sort((a, b) => sortMode === 'relevance' ? normalizedScore(b) - normalizedScore(a) || Number(b.publishedTs || 0) - Number(a.publishedTs || 0) : Number(b.publishedTs || 0) - Number(a.publishedTs || 0));
    const visible = Math.min(rows.length, renderedCount);
    renderStatus(rows.length, visible);
    if (!rows.length) {
      root.innerHTML = newsState.loading ? '' : '<div class="my-hub-v41-empty"><strong>최근 뉴스가 없습니다.</strong><span>다른 종목을 선택하거나 잠시 후 다시 확인해 주세요.</span></div>';
      if (more) more.hidden = true;
      emitRendered();
      return;
    }
    root.innerHTML = rows.slice(0, renderedCount).map((item) => {
      const target = detailTarget(item);
      const relation = relationFor(item, activeSymbol);
      const labels = activeSymbol === 'ALL' ? (item.relatedSymbols || []).map((s) => item.relatedNames?.[s] || s).join(' · ') : (item.relatedNames?.[activeSymbol] || target.name);
      return `<article class="my-hub-v41-news-row" data-related-symbols="${esc((item.relatedSymbols || []).join(','))}" data-news-summary-seed="${esc(item.summarySeed || '')}">
        <div class="my-hub-v41-news-main"><div class="my-hub-v41-news-kicker"><span>${esc(labels || target.name)}</span><i>${esc(category(item))}</i><i class="my-hub-v42-relation" title="${esc(relation.basis)}">${esc(relation.label)}</i></div><h4 title="${esc(item.title)}">${esc(item.title)}</h4><div class="my-hub-v41-meta"><span>${esc(item.source || '원문')}</span><span>${esc(relativeTime(item.publishedAt))}</span></div></div>
        <div class="my-hub-v41-news-actions"><button type="button" data-v41-detail="${esc(target.symbol)}" data-v41-name="${esc(target.name)}">상세</button><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원문</a></div>
      </article>`;
    }).join('');
    if (more) more.hidden = rows.length <= renderedCount;
    emitRendered();
  }

  async function loadNews(force = false) {
    const seq = ++loadSeq;
    controller?.abort(); controller = null;
    const rows = watchlistRows();
    const key = requestKey(rows);
    ensureActiveSymbol(rows); renderChips(rows);
    if (!rows.length) {
      newsItems = []; groups = []; lastSuccessKey = ''; renderedCount = PAGE_SIZE;
      Object.assign(newsState, { requestedAt: Date.now(), receivedAt: 0, lastError: null, isStale: false, partialFailures: 0, loading: false, key: '' });
      renderFeed(); emitState();
      return;
    }
    if (key !== lastSuccessKey) { newsItems = []; groups = []; renderedCount = PAGE_SIZE; }
    controller = new AbortController();
    Object.assign(newsState, { requestedAt: Date.now(), lastError: null, isStale: false, partialFailures: 0, loading: true, key });
    renderFeed(); emitState();
    try {
      const params = new URLSearchParams({ tickers: rows.map((r) => r.symbol).join(','), names: rows.map((r) => r.name || r.symbol).join('|') });
      if (force) params.set('_', Date.now().toString());
      const res = await fetch(`/api/personalized-news?${params}`, { cache: force ? 'no-store' : 'default', signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (seq !== loadSeq || key !== requestKey(watchlistRows())) return;
      groups = Array.isArray(payload.groups) ? payload.groups : [];
      newsItems = flatten(payload);
      lastSuccessKey = key;
      renderedCount = PAGE_SIZE;
      const failures = groups.filter((g) => g.status === 'error').length;
      Object.assign(newsState, { receivedAt: Date.now(), lastError: null, isStale: false, partialFailures: failures, loading: false, key });
      renderFeed(); emitState();
    } catch (error) {
      if (error?.name === 'AbortError' || seq !== loadSeq || key !== requestKey(watchlistRows())) return;
      Object.assign(newsState, { lastError: String(error?.message || error), isStale: newsItems.length > 0, loading: false, partialFailures: 0, key });
      renderFeed(); emitState();
    }
  }

  function enhanceHomeNews() {
    const section = document.getElementById('home-personal-news-v37');
    const head = section?.querySelector('.news-v40-head');
    if (!head || head.querySelector('[data-v41-news-all]')) return;
    const button = document.createElement('button');
    button.type = 'button'; button.dataset.v41NewsAll = '1'; button.className = 'v41-news-all'; button.textContent = '전체보기 →';
    button.addEventListener('click', () => window.__openMyNewsV41());
    head.appendChild(button);
  }

  window.__openMyNewsV41 = () => { window.__openAppTab?.('watchlist'); setTimeout(() => { ensureHub(); setView('news'); }, 60); };
  window.__openMyHubV41 = (view = 'stocks') => { window.__openAppTab?.('watchlist'); setTimeout(() => setView(view), 60); };
  window.__chartViewMyNewsState = newsState;

  function settle() { ensureHub(); enhanceHomeNews(); }
  document.addEventListener('chartview:v37-news-rendered', enhanceHomeNews);
  document.addEventListener('chartview:watchlist-change', () => { if (activeView === 'news') loadNews(true); });
  document.addEventListener('click', (event) => { if (event.target.closest('.app-bottom-btn[data-app-mode="watchlist"]')) setTimeout(settle, 30); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { settle(); setTimeout(settle, 500); }, { once: true });
  else { settle(); setTimeout(settle, 500); }
})();
