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
    const seen = new Set();
    const rows = [];
    for (const group of Array.isArray(payload?.groups) ? payload.groups : []) {
      for (const item of Array.isArray(group?.items) ? group.items : []) {
        const key = item.url || `${item.symbol}|${item.title}`;
        if (!key || seen.has(key)) continue;
        seen.add(key);
        rows.push({ ...item, name: item.name || group.name || item.symbol });
      }
    }
    if (!rows.length) {
      for (const item of Array.isArray(payload?.items) ? payload.items : []) rows.push(item);
    }
    return rows;
  }

  function ensureHub() {
    const tab = document.getElementById('watchlist-tab');
    const main = tab?.querySelector('.watchlist-v30');
    if (!tab || !main) return false;
    tab.dataset.myHubVersion = 'v41';
    const head = main.querySelector('.watchlist-v30-head');
    if (head) {
      const title = head.querySelector('h2');
      const intro = head.querySelector('p');
      if (title) title.textContent = 'MY 관심';
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
    ensureHub();
    applyView();
    if (activeView === 'news') {
      loadNews(false);
      if (options.scroll !== false) document.querySelector('[data-v41-news]')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }

  function renderChips(rows) {
    const root = document.querySelector('[data-v41-chips]');
    if (!root) return;
    root.innerHTML = [`<button type="button" data-v41-symbol="ALL" class="${activeSymbol === 'ALL' ? 'active' : ''}">전체</button>`, ...rows.map((row) => `<button type="button" data-v41-symbol="${esc(row.symbol)}" class="${activeSymbol === row.symbol ? 'active' : ''}">${esc(row.name || row.symbol)}</button>`)].join('');
    root.querySelectorAll('[data-v41-symbol]').forEach((button) => button.addEventListener('click', () => {
      activeSymbol = button.dataset.v41Symbol || 'ALL'; renderedCount = PAGE_SIZE; renderChips(rows); renderFeed();
    }));
  }

  function renderFeed() {
    const root = document.querySelector('[data-v41-feed]');
    const status = document.querySelector('[data-v41-status]');
    const more = document.querySelector('[data-v41-more]');
    if (!root) return;
    document.querySelectorAll('[data-v41-sort]').forEach((b) => b.classList.toggle('active', b.dataset.v41Sort === sortMode));
    let rows = newsItems.filter((item) => activeSymbol === 'ALL' || item.symbol === activeSymbol);
    rows = [...rows].sort((a, b) => sortMode === 'relevance' ? normalizedScore(b) - normalizedScore(a) || Number(b.publishedTs || 0) - Number(a.publishedTs || 0) : Number(b.publishedTs || 0) - Number(a.publishedTs || 0));
    if (status) status.textContent = rows.length ? `${rows.length}건 중 ${Math.min(rows.length, renderedCount)}건 표시` : '표시할 뉴스가 없습니다.';
    if (!rows.length) { root.innerHTML = '<div class="my-hub-v41-empty"><strong>최근 뉴스가 없습니다.</strong><span>다른 종목을 선택하거나 잠시 후 다시 확인해 주세요.</span></div>'; if (more) more.hidden = true; return; }
    root.innerHTML = rows.slice(0, renderedCount).map((item) => `<article class="my-hub-v41-news-row">
      <div class="my-hub-v41-news-main"><div class="my-hub-v41-news-kicker"><span>${esc(item.name || item.symbol)}</span><i>${esc(category(item))}</i></div><h4 title="${esc(item.title)}">${esc(item.title)}</h4><div class="my-hub-v41-meta"><span>${esc(item.source || '원문')}</span><span>${esc(relativeTime(item.publishedAt))}</span></div></div>
      <div class="my-hub-v41-news-actions"><button type="button" data-v41-detail="${esc(item.symbol)}" data-v41-name="${esc(item.name || item.symbol)}">상세</button><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원문</a></div>
    </article>`).join('');
    root.querySelectorAll('[data-v41-detail]').forEach((button) => button.addEventListener('click', () => window.__openStockDetail?.(button.dataset.v41Detail, button.dataset.v41Name)));
    if (more) more.hidden = rows.length <= renderedCount;
  }

  async function loadNews(force = false) {
    const rows = watchlistRows();
    renderChips(rows);
    const status = document.querySelector('[data-v41-status]');
    const feed = document.querySelector('[data-v41-feed]');
    if (!rows.length) { newsItems = []; groups = []; if (status) status.textContent = '관심종목을 추가하면 뉴스가 표시됩니다.'; if (feed) feed.innerHTML = ''; return; }
    const seq = ++loadSeq;
    controller?.abort(); controller = new AbortController();
    if (status) status.textContent = `${rows.length}개 관심종목 뉴스를 불러오는 중…`;
    try {
      const params = new URLSearchParams({ tickers: rows.map((r) => r.symbol).join(','), names: rows.map((r) => r.name || r.symbol).join('|') });
      if (force) params.set('_', Date.now().toString());
      const res = await fetch(`/api/personalized-news?${params}`, { cache: force ? 'no-store' : 'default', signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (seq !== loadSeq) return;
      groups = Array.isArray(payload.groups) ? payload.groups : [];
      newsItems = flatten(payload);
      renderedCount = PAGE_SIZE;
      renderFeed();
      const failures = groups.filter((g) => g.status === 'error').length;
      if (failures && status) status.textContent += ` · ${failures}개 종목 조회 실패`;
    } catch (error) {
      if (error?.name === 'AbortError' || seq !== loadSeq) return;
      if (status) status.textContent = '뉴스를 불러오지 못했습니다. 새로고침으로 다시 시도해 주세요.';
      if (feed) feed.innerHTML = '';
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

  window.__openMyNewsV41 = () => {
    window.__openAppTab?.('watchlist');
    setTimeout(() => { ensureHub(); setView('news'); }, 60);
  };
  window.__openMyHubV41 = (view = 'stocks') => { window.__openAppTab?.('watchlist'); setTimeout(() => setView(view), 60); };

  function settle() { ensureHub(); enhanceHomeNews(); }
  document.addEventListener('chartview:v37-news-rendered', enhanceHomeNews);
  document.addEventListener('chartview:watchlist-change', () => { if (activeView === 'news') loadNews(true); });
  document.addEventListener('click', (event) => { if (event.target.closest('.app-bottom-btn[data-app-mode="watchlist"]')) setTimeout(settle, 30); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { settle(); setTimeout(settle, 500); }, { once: true });
  else { settle(); setTimeout(settle, 500); }
})();