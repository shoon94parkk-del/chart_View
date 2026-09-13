from pathlib import Path


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace(path, old, new, count=1):
    text = read(path)
    if old not in text:
        raise SystemExit(f'missing pattern: {path}: {old[:100]}')
    text = text.replace(old, new, count)
    write(path, text)


# R01: detail state emits an explicit lifecycle event.
replace('static/js/app_state_v40.js', '''  const detail = { open: false, symbol: '', name: '', seq: 0 };
  function beginDetail(symbol, name) {
    detail.open = true;
    detail.symbol = normalizeSymbol(symbol);
    detail.name = String(name || detail.symbol);
    detail.seq += 1;
    return { ...detail };
  }
  function closeDetail() {
    detail.open = false;
    detail.seq += 1;
    return { ...detail };
  }
''', '''  const detail = { open: false, symbol: '', name: '', seq: 0 };
  function emitDetailChange() {
    document.dispatchEvent(new CustomEvent('chartview:detail-change', { detail: { ...detail } }));
  }
  function beginDetail(symbol, name) {
    detail.open = true;
    detail.symbol = normalizeSymbol(symbol);
    detail.name = String(name || detail.symbol);
    detail.seq += 1;
    emitDetailChange();
    return { ...detail };
  }
  function closeDetail() {
    detail.open = false;
    detail.seq += 1;
    emitDetailChange();
    return { ...detail };
  }
''')

# R01: visibility repair is narrowly scoped and cannot steal an intentional menu navigation.
write('static/js/detail_visibility_v40_1.js', r'''(() => {
  'use strict';
  if (window.__chartViewDetailVisibilityV401Installed) return;
  window.__chartViewDetailVisibilityV401Installed = true;

  let scheduled = false;
  let repairing = false;
  let targetObserver = null;
  let bindTimer = null;

  function detailIsCurrent() {
    if (!window.ChartViewState?.detail?.open) return false;
    const state = history.state || {};
    return !state.chartView || state.view === 'detail';
  }

  function repairVisibility() {
    scheduled = false;
    if (repairing || !detailIsCurrent()) return;
    const section = document.getElementById('stock-detail-v40');
    const chartTab = document.getElementById('chart-tab');
    if (!section || !chartTab) return;
    const tabVisible = chartTab.classList.contains('active') && !chartTab.hidden;
    const sectionVisible = !section.hidden;
    if (tabVisible && sectionVisible) return;

    repairing = true;
    try {
      if (!tabVisible && detailIsCurrent()) {
        if (typeof window.__openAppTab === 'function') window.__openAppTab('chart', { history: false });
        else if (typeof window.switchTab === 'function') window.switchTab('chart');
      }
      if (detailIsCurrent()) {
        section.hidden = false;
        document.body.classList.add('app-detail-v40-open');
      }
    } finally {
      queueMicrotask(() => { repairing = false; });
    }
  }

  function scheduleRepair() {
    if (scheduled || !detailIsCurrent()) return;
    scheduled = true;
    requestAnimationFrame(repairVisibility);
  }

  function bindTargets(attempt = 0) {
    clearTimeout(bindTimer);
    targetObserver?.disconnect();
    const chartTab = document.getElementById('chart-tab');
    const section = document.getElementById('stock-detail-v40');
    const targets = [chartTab, section].filter(Boolean);
    if (targets.length) {
      targetObserver = new MutationObserver(scheduleRepair);
      targets.forEach((node) => targetObserver.observe(node, { attributes: true, attributeFilter: ['class', 'hidden'] }));
    }
    if ((!chartTab || !section) && attempt < 20) bindTimer = setTimeout(() => bindTargets(attempt + 1), 250);
    scheduleRepair();
  }

  document.addEventListener('chartview:detail-change', (event) => {
    if (event.detail?.open) bindTargets();
    else { scheduled = false; targetObserver?.disconnect(); }
  });
  window.addEventListener('popstate', () => requestAnimationFrame(scheduleRepair));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => bindTargets(), { once: true });
  else bindTargets();
})();
''')

# R01: user bottom/context navigation explicitly exits detail, aborts requests, and replaces the detail history entry.
replace('static/js/ux_v3.js', '''  function wrapSwitchTab() {
''', '''  function navigateUserTab(tabId) {
    const resolved = tabId === 'market' ? 'macro' : tabId;
    const leavingDetail = Boolean(window.ChartViewState?.detail?.open || history.state?.view === 'detail');
    if (!leavingDetail) return openTab(tabId);
    if (typeof window.__closeStockDetail === 'function') window.__closeStockDetail({ force: true, restore: false });
    openTab(tabId, { history: false });
    try { history.replaceState({ chartView: true, tab: resolved }, '', location.href); } catch (_) { }
  }

  function wrapSwitchTab() {
''')
replace('static/js/ux_v3.js', '''        openTab(button.dataset.appTab);
''', '''        navigateUserTab(button.dataset.appTab);
''')
replace('static/js/ux_v3.js', '''        if (button.classList.contains('active')) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        if (mode === 'home') openTab('home');
        else if (mode === 'watchlist') openTab('watchlist');
        else if (mode === 'analysis') openTab(lastAnalysis);
        else if (mode === 'discover') openTab(lastDiscover);
        else if (mode === 'market') openTab(lastMarket);
''', '''        if (button.classList.contains('active') && !window.ChartViewState?.detail?.open) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        if (mode === 'home') navigateUserTab('home');
        else if (mode === 'watchlist') navigateUserTab('watchlist');
        else if (mode === 'analysis') navigateUserTab(lastAnalysis);
        else if (mode === 'discover') navigateUserTab(lastDiscover);
        else if (mode === 'market') navigateUserTab(lastMarket);
''')

# Structural market-ready event fixes the V41 MY test race instead of increasing timeouts.
replace('static/js/home_market_v9.js', '''    if (anchor && anchor.parentElement === home) home.insertBefore(panel, anchor);
    else home.prepend(panel);
    return panel;
''', '''    if (anchor && anchor.parentElement === home) home.insertBefore(panel, anchor);
    else home.prepend(panel);
    document.dispatchEvent(new CustomEvent('chartview:market-panel-ready', { detail: { id: panel.id } }));
    return panel;
''')
replace('static/js/home_polish_v41_4.js', '''  document.addEventListener('chartview:v37-news-rendered', () => requestAnimationFrame(sync));
''', '''  document.addEventListener('chartview:v37-news-rendered', () => requestAnimationFrame(sync));
  document.addEventListener('chartview:market-panel-ready', () => requestAnimationFrame(syncMarketToggle));
''')
replace('static/js/home_polish_v41_4.js', '''    button.innerHTML = `<span>금리 · VIX · 유가 · 환율</span><strong>${expanded ? '접기' : `${hiddenCount}개 더보기`}</strong><i>⌄</i>`;
''', '''    button.innerHTML = `<span>금리 · VIX · 유가 · 환율</span><strong>${expanded ? '접기' : `${hiddenCount}개 더보기`}</strong>`;
''')

# R07: relation is explicitly classified, separate from investment-event importance.
replace('news_service_v37.py', '''def _news_score(title: str, published_ts: float, market: str, name: str, symbol: str, context: str = "") -> float:
''', '''def _relation_meta(title: str, context: str, name: str, symbol: str) -> tuple[str, str]:
    title_l = title.lower()
    context_l = context.lower()
    name_l = (name or "").strip().lower()
    bare = symbol.split(".")[0].lower()
    title_hit = bool(name_l and name_l in title_l) or bool(len(bare) >= 2 and re.search(rf"(?<![a-z0-9]){re.escape(bare)}(?![a-z0-9])", title_l))
    context_hit = bool(name_l and name_l in context_l) or bool(len(bare) >= 2 and re.search(rf"(?<![a-z0-9]){re.escape(bare)}(?![a-z0-9])", context_l))
    if title_hit:
        return "direct", "제목에 기업명·티커 확인"
    if context_hit:
        return "direct", "제공처 기사 요약에 기업명·티커 확인"
    return "related", "제공처 종목 태그 기준 · 공급망/경쟁/업종 연관 가능"


def _news_score(title: str, published_ts: float, market: str, name: str, symbol: str, context: str = "") -> float:
''')
replace('news_service_v37.py', '''        investment_score, investment_tags = _investment_relevance(title, context, "KR")
        items.append({
''', '''        investment_score, investment_tags = _investment_relevance(title, context, "KR")
        relation_type, relation_basis = _relation_meta(title, context, name, symbol)
        items.append({
''')
replace('news_service_v37.py', '''            "investmentTags": investment_tags,
        })
''', '''            "investmentTags": investment_tags,
            "relationType": relation_type,
            "relationBasis": relation_basis,
        })
''', 1)
replace('news_service_v37.py', '''        investment_score, investment_tags = _investment_relevance(title, context, "US")
        items.append({
''', '''        investment_score, investment_tags = _investment_relevance(title, context, "US")
        relation_type, relation_basis = _relation_meta(title, context, name, symbol)
        items.append({
''')
# second occurrence
text = read('news_service_v37.py')
needle = '''            "investmentTags": investment_tags,\n        })'''
pos = text.find(needle, text.find('def _fetch_finnhub_news'))
if pos < 0:
    raise SystemExit('finnhub investmentTags block missing')
text = text[:pos] + '''            "investmentTags": investment_tags,\n            "relationType": relation_type,\n            "relationBasis": relation_basis,\n        })''' + text[pos+len(needle):]
write('news_service_v37.py', text)

# R03-R08: MY news owns request/success/error state and article identity.
write('static/js/my_hub_v41.js', r'''(() => {
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
      return `<article class="my-hub-v41-news-row" data-related-symbols="${esc((item.relatedSymbols || []).join(','))}">
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
''')

# R03/R04: resilience is event-driven, does not infer successful fetches from DOM text or restore raw HTML snapshots.
write('static/js/resilience_v41_3.js', r'''(() => {
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
''')

# R08: preserve full title-derived summary text and enhance MY rows on their own render event.
replace('static/js/news_readability_v41_2.js', '''    const type = eventType(raw);
    const core = withoutCompany.length > 72 ? `${withoutCompany.slice(0, 69)}…` : withoutCompany;
    return `${type} 관련 소식으로, 제목 기준 핵심은 “${core}”입니다.`;
''', '''    const type = eventType(raw);
    return `${type} · ${withoutCompany}`;
''')
replace('static/js/news_readability_v41_2.js', '''  document.addEventListener('chartview:v37-news-rendered', () => { attachNewsObserver(); schedule(); });
''', '''  document.addEventListener('chartview:v37-news-rendered', () => { attachNewsObserver(); schedule(); });
  document.addEventListener('chartview:v41-news-rendered', schedule);
''')
replace('static/js/news_readability_v41_2.js', "home.dataset.newsReadability = 'v41.7'", "home.dataset.newsReadability = 'v42'")
replace('static/js/news_readability_v41_2.js', "hub.dataset.newsReadability = 'v41.7'", "hub.dataset.newsReadability = 'v42'")

# R07: Home labels separate investment importance from direct/related relationship.
replace('static/js/personalized_news_v40.js', '''  function impactScore(item) {
    const raw = Number(item?.score || 0);
    return Math.max(1, Math.min(100, Math.round((raw - 40) / 1.45)));
  }
''', '''  function impactScore(item) {
    const raw = Number(item?.score || 0);
    let value = Math.max(1, Math.min(100, Math.round((raw - 40) / 1.45)));
    if (item?.relationType && item.relationType !== 'direct') value = Math.min(value, 69);
    return value;
  }

  function relationMeta(item) {
    return item?.relationType === 'direct'
      ? { label: '직접 관련', note: item?.relationBasis || '제목·기사 요약에서 기업명을 확인했습니다.' }
      : { label: '업종·연관', note: item?.relationBasis || '제공처 종목 태그 기준의 공급망·경쟁·업종 연관 기사입니다.' };
  }
''')
replace('static/js/personalized_news_v40.js', '''  function referenceNote(item) {
    const title = String(item?.title || '').toLowerCase();
''', '''  function referenceNote(item) {
    const title = String(item?.title || '').toLowerCase();
    const relation = relationMeta(item);
''')
replace('static/js/personalized_news_v40.js', '''    for (const [pattern, text] of rules) if (pattern.test(title)) return text;
    return '관심종목과 직접 관련된 최신 기사입니다. 제목 기준 분류이며 기사 본문을 분석한 결론은 아닙니다.';
''', '''    for (const [pattern, text] of rules) if (pattern.test(title)) return `${relation.label} · ${text}`;
    return `${relation.label} · ${relation.note} 제목 기준 사건 분류이며 기사 본문을 분석한 결론은 아닙니다.`;
''')
replace('static/js/personalized_news_v40.js', '''      const meta = impactMeta(impactScore(item));
      return `<article class="news-v40-card ${index === 0 ? 'is-lead' : ''}" data-impact="${meta.level}" data-news-symbol="${esc(item.symbol)}">
        <div class="news-v40-top"><div><b>${esc(item.name || item.symbol)}</b><span>${esc(item.symbol)}</span></div><em>${meta.label}</em></div>
''', '''      const meta = impactMeta(impactScore(item));
      const relation = relationMeta(item);
      return `<article class="news-v40-card ${index === 0 ? 'is-lead' : ''}" data-impact="${meta.level}" data-news-symbol="${esc(item.symbol)}">
        <div class="news-v40-top"><div><b>${esc(item.name || item.symbol)}</b><span>${esc(item.symbol)}</span></div><em title="${esc(relation.note)}">${meta.label} · ${relation.label}</em></div>
''')

# R09/R10: single-detail chart keeps dates/return values and exposes readable selection; internal basis names become user language.
replace('static/js/single_detail_v40.js', '''  function extractSeries(stock) {
    const rows = Array.isArray(stock?.data) ? stock.data : [];
    return rows.map((row) => {
      if (typeof row === 'number') return row;
      if (!row || typeof row !== 'object') return null;
      const state = D()?.numberState?.(row.value ?? row.return ?? row.close ?? row.price);
      return state?.kind === 'number' ? state.value : null;
    }).filter((value) => value !== null);
  }

  function sparkline(values) {
    if (!Array.isArray(values) || values.length < 2) return '<div class="detail-v40-chart-empty">차트 자료 없음</div>';
    const nums = values.slice(-80);
    const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
    const width = 720, height = 220, pad = 12;
    const points = nums.map((v, index) => {
      const x = pad + (index / Math.max(1, nums.length - 1)) * (width - pad * 2);
      const y = height - pad - ((v - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg class="detail-v40-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="1달 수익률 흐름"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="4" vector-effect="non-scaling-stroke"/></svg>`;
  }
''', '''  function extractSeries(stock) {
    const rows = Array.isArray(stock?.data) ? stock.data : [];
    return rows.map((row, index) => {
      if (typeof row === 'number') return { time: null, value: row, index };
      if (!row || typeof row !== 'object') return null;
      const state = D()?.numberState?.(row.value ?? row.return ?? row.close ?? row.price);
      return state?.kind === 'number' ? { time: row.time ?? row.date ?? null, value: state.value, index } : null;
    }).filter(Boolean);
  }

  function pointDate(point) {
    if (!point?.time) return '';
    const date = typeof point.time === 'number' ? new Date(point.time * 1000) : new Date(point.time);
    return Number.isFinite(date.getTime()) ? date.toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' }) : '';
  }

  function sparkline(series) {
    if (!Array.isArray(series) || series.length < 2) return '<div class="detail-v40-chart-empty">차트 자료 없음</div>';
    const points = series.slice(-80);
    const nums = points.map((row) => row.value);
    const min = Math.min(...nums), max = Math.max(...nums);
    const low = min === max ? min - 1 : min, high = min === max ? max + 1 : max, span = high - low;
    const width = 720, height = 220, left = 54, right = 12, top = 16, bottom = 22;
    const xy = points.map((row, index) => {
      const x = left + (index / Math.max(1, points.length - 1)) * (width - left - right);
      const y = height - bottom - ((row.value - low) / span) * (height - top - bottom);
      return { x, y };
    });
    const poly = xy.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const zeroY = low <= 0 && high >= 0 ? height - bottom - ((0 - low) / span) * (height - top - bottom) : null;
    return `<div class="detail-v42-chart-wrap" data-detail-chart tabindex="0" aria-label="1달 수익률 차트. 좌우 화살표 또는 터치로 날짜별 값을 확인할 수 있습니다.">
      <div class="detail-v42-chart-readout" data-detail-chart-readout>터치하거나 좌우키로 날짜별 수익률 확인</div>
      <svg class="detail-v40-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="1달 수익률 흐름">
        ${zeroY === null ? '' : `<line class="detail-v42-zero" x1="${left}" x2="${width-right}" y1="${zeroY.toFixed(1)}" y2="${zeroY.toFixed(1)}"/>`}
        <text class="detail-v42-y-label" x="4" y="${top + 4}">${max.toFixed(1)}%</text>
        <text class="detail-v42-y-label" x="4" y="${height-bottom}">${min.toFixed(1)}%</text>
        <polyline points="${poly}" fill="none" stroke="currentColor" stroke-width="4" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="detail-v42-chart-axis"><span>${esc(pointDate(points[0]) || '시작')}</span><span>${esc(pointDate(points.at(-1)) || '현재')}</span></div>
    </div>`;
  }

  function bindChart(section, series) {
    const root = section.querySelector('[data-detail-chart]');
    const svg = root?.querySelector('svg');
    const readout = root?.querySelector('[data-detail-chart-readout]');
    const points = Array.isArray(series) ? series.slice(-80) : [];
    if (!root || !svg || !readout || !points.length) return;
    let index = points.length - 1;
    const select = (next) => {
      index = Math.max(0, Math.min(points.length - 1, next));
      const point = points[index];
      readout.textContent = `${pointDate(point) || `${index + 1}번째 관측`} · ${D()?.formatPercent?.(point.value, 2) || `${point.value.toFixed(2)}%`}`;
    };
    const fromPointer = (event) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      select(Math.round(ratio * (points.length - 1)));
    };
    root.addEventListener('pointerdown', fromPointer);
    root.addEventListener('pointermove', (event) => { if (event.pointerType === 'touch' || event.buttons) fromPointer(event); });
    root.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft') { event.preventDefault(); select(index - 1); }
      if (event.key === 'ArrowRight') { event.preventDefault(); select(index + 1); }
    });
    select(index);
  }
''')
replace('static/js/single_detail_v40.js', '''    const priceBasis = stock?.priceBasis || stock?.meta?.priceBasis || stock?.basisLabel || 'API 제공 가격 기준';
    return { start, end, priceBasis };
''', '''    const rawBasis = stock?.priceBasis || stock?.meta?.priceBasis || stock?.basisLabel || '';
    const priceBasis = rawBasis === 'adjusted_close' ? '조정주가' : rawBasis === 'close' ? '종가' : (rawBasis || 'API 제공 가격 기준');
    return { start, end, priceBasis };
''')
replace('static/js/single_detail_v40.js', '''    bindBack(section);
    bindActions(section, symbol, name);
    bindTabs(section);
''', '''    bindBack(section);
    bindActions(section, symbol, name);
    bindTabs(section);
    bindChart(section, series);
''')

# Styling for relation labels and readable interactive detail chart.
my_css = read('static/css/my_hub_v41.css')
if 'V42 prelaunch relation badge' not in my_css:
    my_css += '''\n/* V42 prelaunch relation badge */\n.my-hub-v41-news-kicker .my-hub-v42-relation{background:#f3f4f6;color:#4b5563}.my-hub-v41-status[data-stale="true"]{border:1px solid #f59e0b;background:#fffbeb;color:#92400e;padding:9px 11px;border-radius:11px}.my-hub-v413-freshness{display:block;margin-top:4px;font-size:10.5px;font-weight:700;color:#64748b}@media(prefers-color-scheme:dark){.my-hub-v41-news-kicker .my-hub-v42-relation{background:#273244;color:#cbd5e1}.my-hub-v41-status[data-stale="true"]{border-color:#92400e;background:#451a03;color:#fde68a}}\n'''
write('static/css/my_hub_v41.css', my_css)

detail_css = read('static/css/detail_ui_v40.css')
if 'V42 interactive detail chart' not in detail_css:
    detail_css += '''\n/* V42 interactive detail chart */\n.detail-v42-chart-wrap{width:100%;outline:none}.detail-v42-chart-readout{min-height:24px;padding:3px 8px;color:#315b9e;font-size:12px;font-weight:800;text-align:right}.detail-v42-chart-axis{display:flex;justify-content:space-between;padding:0 8px 2px;color:#8a94a3;font-size:10px}.detail-v42-zero{stroke:#94a3b8;stroke-width:1;stroke-dasharray:5 5;opacity:.7}.detail-v42-y-label{fill:#8a94a3;font-size:10px}.detail-v42-chart-wrap:focus-visible{outline:2px solid #2563eb;outline-offset:2px;border-radius:10px}@media(max-width:720px){.detail-v42-chart-readout{font-size:11px}.detail-v40-chart-svg{touch-action:none}}\n'''
write('static/css/detail_ui_v40.css', detail_css)

# Cache-bust all touched client assets.
boot = read('static/js/home_watchlist_boot_v32c.js')
repls = {
    '/static/js/app_state_v40.js?v=20260913stage12': '/static/js/app_state_v40.js?v=20260913v42',
    '/static/js/single_detail_v40.js?v=20260913stage12': '/static/js/single_detail_v40.js?v=20260913v42',
    '/static/js/detail_visibility_v40_1.js?v=20260913v401': '/static/js/detail_visibility_v40_1.js?v=20260913v42',
    '/static/js/personalized_news_v40.js?v=20260913v415': '/static/js/personalized_news_v40.js?v=20260913v42',
    '/static/js/my_hub_v41.js?v=20260913v41': '/static/js/my_hub_v41.js?v=20260913v42',
    '/static/css/my_hub_v41.css?v=20260913v41': '/static/css/my_hub_v41.css?v=20260913v42',
    '/static/js/news_readability_v41_2.js?v=20260913v417': '/static/js/news_readability_v41_2.js?v=20260913v42',
    '/static/css/news_readability_v41_2.css?v=20260913v417': '/static/css/news_readability_v41_2.css?v=20260913v42',
    '/static/js/resilience_v41_3.js?v=20260913v413': '/static/js/resilience_v41_3.js?v=20260913v42',
    '/static/css/detail_ui_v40.css?v=20260913stage12': '/static/css/detail_ui_v40.css?v=20260913v42',
    '/static/js/home_polish_v41_4.js?v=20260913v415b': '/static/js/home_polish_v41_4.js?v=20260913v42',
}
for old, new in repls.items():
    if old not in boot:
        print('WARN cache token not found:', old)
    boot = boot.replace(old, new)
write('static/js/home_watchlist_boot_v32c.js', boot)

html = read('templates/index.html')
html = html.replace('/static/js/home_watchlist_boot_v32c.js?v=20260913v417', '/static/js/home_watchlist_boot_v32c.js?v=20260913v42')
write('templates/index.html', html)

# R02: tests verify current functional contracts instead of frozen historical cache literals.
write('tests/test_v41_2_news_readability.py', '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_news_readability_assets_and_markers_are_loaded():\n    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')\n    js = (ROOT / 'static/js/news_readability_v41_2.js').read_text(encoding='utf-8')\n    assert '/static/css/news_readability_v41_2.css?v=' in boot\n    assert '/static/js/news_readability_v41_2.js?v=' in boot\n    assert "newsReadability = 'v42'" in js\n\ndef test_summary_and_market_context_contract():\n    js = (ROOT / 'static/js/news_readability_v41_2.js').read_text(encoding='utf-8')\n    css = (ROOT / 'static/css/news_readability_v41_2.css').read_text(encoding='utf-8')\n    for text in ('한줄 요약', '제목 기준', '최근 2거래일 반등', '최근 2거래일 약세', '기간 고점권', '기간 저점권', '5거래일 전', '현재'):\n        assert text in js\n    assert "chartview:v41-news-rendered" in js\n    assert "slice(0, 69)" not in js\n    assert 'observer.observe(document.documentElement' not in js\n    assert '.news-v412-summary.is-expanded' in css\n''')
write('tests/test_v41_5_consistency.py', '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_five_day_chart_uses_daily_period_basis():\n    market = (ROOT / 'market_service.py').read_text(encoding='utf-8')\n    assert '\"5d\": \"1d\"' in market\n\ndef test_home_news_sparkline_uses_full_five_day_series():\n    js = (ROOT / 'static/js/personalized_news_v40.js').read_text(encoding='utf-8')\n    assert '.slice(-20)' not in js\n    assert 'pickDiverse(payload?.items, TOP_COUNT)' in js\n\ndef test_market_has_one_canonical_toggle_and_ready_event():\n    polish = (ROOT / 'static/js/home_polish_v41_4.js').read_text(encoding='utf-8')\n    market = (ROOT / 'static/js/home_market_v9.js').read_text(encoding='utf-8')\n    assert 'data-v415-market-toggle' in polish\n    assert 'chartview:market-panel-ready' in polish and 'chartview:market-panel-ready' in market\n    assert '<i>⌄</i>' not in polish\n\ndef test_current_client_assets_are_cache_busted():\n    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')\n    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')\n    for name in ('personalized_news_v40.js','news_readability_v41_2.js','my_hub_v41.js','resilience_v41_3.js','single_detail_v40.js','detail_visibility_v40_1.js','home_polish_v41_4.js'):\n        assert f'/static/js/{name}?v=' in boot\n    assert '/static/js/home_watchlist_boot_v32c.js?v=20260913v42' in html\n''')

write('tests/test_prelaunch_v42.py', '''from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_detail_navigation_has_no_global_visibility_observer():\n    vis=(ROOT/'static/js/detail_visibility_v40_1.js').read_text(encoding='utf-8')\n    nav=(ROOT/'static/js/ux_v3.js').read_text(encoding='utf-8')\n    assert 'observer.observe(document.body' not in vis\n    assert 'observer.observe(document.documentElement' not in vis\n    assert 'navigateUserTab' in nav and '__closeStockDetail' in nav and 'history.replaceState' in nav\n\ndef test_news_state_is_event_driven_and_no_html_snapshot_restore():\n    hub=(ROOT/'static/js/my_hub_v41.js').read_text(encoding='utf-8')\n    resilience=(ROOT/'static/js/resilience_v41_3.js').read_text(encoding='utf-8')\n    assert 'receivedAt' in hub and 'lastSuccessKey' in hub and 'chartview:v41-news-state' in hub\n    assert 'relatedSymbols' in hub and 'relations' in hub\n    assert 'feedSnapshot' not in resilience and 'feed.innerHTML = feedSnapshot' not in resilience\n    assert 'MutationObserver' not in resilience\n    assert 'chartview:v41-news-state' in resilience\n\ndef test_relation_and_chart_readability_contracts():\n    service=(ROOT/'news_service_v37.py').read_text(encoding='utf-8')\n    detail=(ROOT/'static/js/single_detail_v40.js').read_text(encoding='utf-8')\n    assert '_relation_meta' in service and 'relationType' in service and 'relationBasis' in service\n    assert '조정주가' in detail and 'data-detail-chart-readout' in detail and 'ArrowLeft' in detail and 'detail-v42-zero' in detail\n''')

# Dynamic regression is intentionally permanent for release candidates.
write('tests/prelaunch_v42.cjs', r'''const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const BASE = process.env.APP_URL || 'http://127.0.0.1:8080';
const watch = [{symbol:'NVDA',name:'엔비디아'},{symbol:'AAPL',name:'애플'}];
const shared = {symbol:'NVDA',name:'엔비디아',title:'NVIDIA and Apple expand AI supply agreement',source:'Test',publishedAt:new Date().toISOString(),publishedTs:Date.now(),url:'https://example.com/shared',score:180,relationType:'direct',relationBasis:'제목에 기업명·티커 확인'};
const payload = {items:[shared],errors:[],groups:[{symbol:'NVDA',name:'엔비디아',status:'success',items:[shared]},{symbol:'AAPL',name:'애플',status:'success',items:[{...shared,symbol:'AAPL',name:'애플',relationType:'direct'}]}]};
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 await context.addInitScript(rows=>localStorage.setItem('chartview-watchlist-v1',JSON.stringify(rows)),watch);
 const page=await context.newPage(); page.setDefaultTimeout(15000);
 let failNews=false; let delayNews=false;
 await page.route('**/api/personalized-news?**',async route=>{ if(delayNews) await new Promise(r=>setTimeout(r,1400)); if(failNews) return route.fulfill({status:500,body:'fail'}); return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)}); });
 await page.route('**/api/compare?**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({stocks:[{ticker:'NVDA',price:100,return:-2.4,startDate:'2026-08-12',endDate:'2026-09-12',priceBasis:'adjusted_close',data:[{time:1754956800,value:0},{time:1755302400,value:2},{time:1755907200,value:-1},{time:1757376000,value:-2.4}]}]})}));
 await page.route('**/api/valuation?**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({stocks:[{}]})}));
 await page.route('**/api/consensus?**',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
 const errors=[]; page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(BASE,{waitUntil:'domcontentloaded'});
 await page.waitForSelector('.app-bottom-btn[data-app-mode="watchlist"]');

 // shared URL belongs to both filters but appears once in ALL.
 await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').tap();
 await page.waitForSelector('[data-v41-view="news"]'); await page.locator('[data-v41-view="news"]').tap();
 await page.waitForSelector('.my-hub-v41-news-row');
 assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);
 await page.locator('[data-v41-symbol="NVDA"]').tap(); assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);
 await page.locator('[data-v41-symbol="AAPL"]').tap(); assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);

 // successful receive timestamp does not change on filter/sort only.
 const received1=await page.evaluate(()=>window.__chartViewMyNewsState.receivedAt);
 await page.locator('[data-v41-sort="relevance"]').tap(); await page.waitForTimeout(100);
 const received2=await page.evaluate(()=>window.__chartViewMyNewsState.receivedAt); assert.equal(received2,received1);

 // failed refresh keeps data and interactions, reports stale, and keeps receivedAt.
 failNews=true; await page.locator('[data-v41-refresh]').tap();
 await page.waitForFunction(()=>window.__chartViewMyNewsState && !window.__chartViewMyNewsState.loading);
 assert.equal(await page.locator('.my-hub-v41-news-row').count(),1);
 assert.match(await page.locator('[data-v41-status]').innerText(),/갱신에 실패/);
 assert.equal(await page.evaluate(()=>window.__chartViewMyNewsState.receivedAt),received1);
 const summary=page.locator('.my-hub-v41-news-row .news-v412-summary').first(); await summary.waitFor(); await summary.tap(); assert.equal(await summary.getAttribute('aria-expanded'),'true');

 // detail -> bottom navigation must close detail and remain on target after late detail work.
 failNews=false; await page.locator('.my-hub-v41-news-row [data-v41-detail]').tap(); await page.waitForSelector('#stock-detail-v40:not([hidden])');
 await page.locator('.app-bottom-btn[data-app-mode="home"]').tap(); await page.waitForSelector('#home-tab',{state:'visible'}); await page.waitForTimeout(2200);
 assert.equal(await page.locator('#stock-detail-v40').isVisible(),false); assert.ok(await page.locator('.app-bottom-btn[data-app-mode="home"]').evaluate(el=>el.classList.contains('active')));

 // stale request cannot repopulate an emptied watchlist.
 await page.locator('.app-bottom-btn[data-app-mode="watchlist"]').tap(); await page.locator('[data-v41-view="news"]').tap(); delayNews=true;
 const refresh=page.locator('[data-v41-refresh]'); await refresh.tap();
 await page.evaluate(()=>{ localStorage.setItem('chartview-watchlist-v1','[]'); document.dispatchEvent(new CustomEvent('chartview:watchlist-change',{detail:{items:[]}})); });
 await page.waitForTimeout(1800);
 assert.equal(await page.locator('.my-hub-v41-news-row').count(),0); assert.equal(await page.evaluate(()=>window.__chartViewMyNewsState.key),'');
 assert.deepEqual(errors,[]);
 console.log('PRELAUNCH_V42_PASS'); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
''')

# Run the new browser regression in both local-mobile and exact-production jobs.
replace('.github/workflows/app-check.yml', '''          node tests/v41_my_hub.cjs
''', '''          node tests/v41_my_hub.cjs
          node tests/prelaunch_v42.cjs
''', 1)
# production occurrence
text = read('.github/workflows/app-check.yml')
prod = '''          node tests/production_stage12.cjs\n          node tests/v41_my_hub.cjs\n'''
if prod in text:
    text = text.replace(prod, prod + '          node tests/prelaunch_v42.cjs\n', 1)
else:
    raise SystemExit('production test block missing')
write('.github/workflows/app-check.yml', text)

print('Prelaunch V42 stabilization applied')
