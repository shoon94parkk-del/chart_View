(() => {
  'use strict';

  if (window.__chartViewNewsV40Installed) return;
  window.__chartViewNewsV40Installed = true;

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const MAX_SYMBOLS = 20;
  const TOP_COUNT = 3;
  let loadSeq = 0;
  let newsController = null;
  const marketCache = new Map();
  const marketInflight = new Map();

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function readWatchlist() {
    if (window.ChartViewState) return window.ChartViewState.getWatchlist().items.slice(0, MAX_SYMBOLS);
    try {
      const raw = localStorage.getItem(WATCHLIST_KEY);
      if (raw === null) return [];
      const rows = JSON.parse(raw);
      return Array.isArray(rows) ? rows.slice(0, MAX_SYMBOLS) : [];
    } catch (_) { return []; }
  }

  function ensureSection() {
    let section = document.getElementById('home-personal-news-v37');
    if (section) {
      section.classList.add('home-personal-news-v40');
      return section;
    }
    const watchlist = document.getElementById('home-watchlist-v30');
    const body = document.getElementById('home-v8-body');
    if (!watchlist && !body) return null;
    section = document.createElement('section');
    section.id = 'home-personal-news-v37';
    section.className = 'home-v8-block home-personal-news-v40';
    if (watchlist) watchlist.insertAdjacentElement('afterend', section);
    else body.insertAdjacentElement('beforebegin', section);
    document.dispatchEvent(new CustomEvent('chartview:v37-news-rendered'));
    return section;
  }

  function relativeTime(value) {
    if (!value) return '';
    const ts = Date.parse(value);
    if (!Number.isFinite(ts)) return '';
    const minutes = Math.max(0, Math.floor((Date.now() - ts) / 60000));
    if (minutes < 60) return `${Math.max(1, minutes)}분 전`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}시간 전`;
    const days = Math.floor(hours / 24);
    return days <= 6 ? `${days}일 전` : new Date(ts).toLocaleDateString('ko-KR', { month:'numeric', day:'numeric' });
  }

  function impactScore(item) {
    const raw = Number(item?.score || 0);
    return Math.max(1, Math.min(100, Math.round((raw - 40) / 1.45)));
  }

  function impactMeta(score) {
    if (score >= 85) return { label: '매우 중요', level: 'critical' };
    if (score >= 70) return { label: '중요', level: 'high' };
    if (score >= 50) return { label: '주목', level: 'medium' };
    return { label: '참고', level: 'low' };
  }

  function referenceNote(item) {
    const title = String(item?.title || '').toLowerCase();
    const rules = [
      [/실적|영업이익|매출|earnings|revenue|guidance/, '실적·가이던스 관련 이벤트입니다. 실제 영향은 원문과 실적 기준을 함께 확인하세요.'],
      [/수주|계약|공급|contract|deal|order/, '수주·계약 관련 이벤트입니다. 계약 규모와 기간은 원문에서 확인하세요.'],
      [/인수|합병|acqui|merger/, '인수합병 관련 이벤트입니다. 거래 조건과 완료 여부를 확인하세요.'],
      [/배당|자사주|buyback|dividend/, '주주환원 관련 이벤트입니다. 기준일과 규모를 확인하세요.'],
      [/승인|fda|규제|sec|소송|lawsuit|리콜|recall/, '규제·법적 이벤트입니다. 확정 여부와 적용 범위를 확인하세요.'],
      [/목표가|투자의견|upgrade|downgrade|forecast/, '시장 전망·의견 관련 기사입니다. 전망 주체와 근거를 확인하세요.'],
    ];
    for (const [pattern, text] of rules) if (pattern.test(title)) return text;
    return '관심종목과 직접 관련된 최신 기사입니다. 제목 기준 분류이며 기사 본문을 분석한 결론은 아닙니다.';
  }

  function renderShell(section) {
    if (section.dataset.v40Shell === '1') return;
    section.dataset.v40Shell = '1';
    section.innerHTML = `
      <div class="home-block-head news-v40-head">
        <div><span>MY NEWS</span><h3>관심종목 핵심 뉴스</h3></div>
        <button type="button" data-news-v40-refresh>↻ 새로고침</button>
      </div>
      <div class="news-v40-status" data-news-v40-status role="status"></div>
      <div class="news-v40-grid" data-news-v40-grid></div>
      <details class="news-v40-groups" data-news-v40-groups><summary>관심종목별 조회 상태</summary><div></div></details>
      <div class="news-v40-foot">기사 본문·이미지는 재게시하지 않으며, 5거래일 미니차트는 기사 반응이 아닌 최근 가격 흐름입니다.</div>`;
    section.querySelector('[data-news-v40-refresh]')?.addEventListener('click', () => loadNews(true));
  }

  function renderStatus(section, text, detail = '') {
    const node = section.querySelector('[data-news-v40-status]');
    if (node) node.innerHTML = `<strong>${esc(text)}</strong>${detail ? `<span>${esc(detail)}</span>` : ''}`;
  }

  function groupStatusHtml(payload, requestedRows) {
    const groups = Array.isArray(payload?.groups) ? payload.groups : [];
    const bySymbol = new Map(groups.map((g) => [g.symbol, g]));
    return requestedRows.map((row) => {
      const group = bySymbol.get(row.symbol);
      const status = group?.status || (group ? ((group.items || []).length ? 'success' : 'no_news') : 'error');
      const label = status === 'success' ? `${(group.items || []).length}건` : status === 'no_news' ? '기사 없음' : '조회 실패';
      return `<span class="news-v40-group ${status}"><b>${esc(row.name || row.symbol)}</b><i>${label}</i></span>`;
    }).join('');
  }

  function renderArticles(section, payload, rows, seq) {
    if (seq !== loadSeq) return;
    const grid = section.querySelector('[data-news-v40-grid]');
    const groups = section.querySelector('[data-news-v40-groups] > div');
    const items = Array.isArray(payload?.items) ? payload.items.slice(0, TOP_COUNT) : [];
    const errors = Array.isArray(payload?.errors) ? payload.errors : [];
    if (groups) groups.innerHTML = groupStatusHtml(payload, rows);

    if (!rows.length) {
      renderStatus(section, '관심종목을 추가하면 뉴스가 표시됩니다.');
      if (grid) grid.innerHTML = '';
      return [];
    }
    if (!items.length) {
      renderStatus(section, errors.length ? '일부 뉴스 제공처에 연결할 수 없습니다.' : '최근 핵심 뉴스가 없습니다.', errors.length ? '종목별 조회 상태를 확인하고 다시 시도할 수 있습니다.' : '새 기사가 확인되면 표시됩니다.');
      if (grid) grid.innerHTML = '';
      return [];
    }

    renderStatus(section, `${rows.length}개 관심종목 · TOP ${items.length}`, errors.length ? `${errors.length}개 종목은 부분 실패 · 정상 결과는 유지했습니다.` : '제목·출처·발행 시각을 먼저 표시했습니다.');
    if (grid) grid.innerHTML = items.map((item, index) => {
      const meta = impactMeta(impactScore(item));
      return `<article class="news-v40-card ${index === 0 ? 'is-lead' : ''}" data-impact="${meta.level}" data-news-symbol="${esc(item.symbol)}">
        <div class="news-v40-top"><div><b>${esc(item.name || item.symbol)}</b><span>${esc(item.symbol)}</span></div><em>${meta.label}</em></div>
        <h4 title="${esc(item.title)}">${esc(item.title)}</h4>
        <p><b>이벤트 참고 설명</b>${esc(referenceNote(item))}</p>
        <div class="news-v40-meta"><span>${esc(item.source || '원문')}</span><i>·</i><span>${esc(relativeTime(item.publishedAt))}</span></div>
        <div class="news-v40-actions"><button type="button" data-news-v40-detail="${esc(item.symbol)}" data-news-v40-name="${esc(item.name || item.symbol)}">상세 보기</button><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원문 보기 →</a></div>
        <details class="news-v40-market"><summary>5거래일 가격 흐름</summary><div data-news-v40-market="${esc(item.symbol)}"><span>가격 흐름 불러오는 중…</span></div></details>
      </article>`;
    }).join('');
    document.dispatchEvent(new CustomEvent('chartview:v37-news-rendered'));
    return items;
  }

  function sparkline(values) {
    const nums = (Array.isArray(values) ? values : []).map(Number).filter(Number.isFinite).slice(-20);
    if (nums.length < 2) return '';
    const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
    const width = 140, height = 40, pad = 2;
    const points = nums.map((value, i) => {
      const x = pad + (i / Math.max(1, nums.length - 1)) * (width - pad * 2);
      const y = height - pad - ((value - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg viewBox="0 0 ${width} ${height}" aria-label="최근 5거래일 가격 흐름"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
  }

  function extractSeries(payload) {
    const stock = payload?.stocks?.[0] || {};
    const rows = stock.data || stock.series || stock.prices || payload?.data || [];
    return Array.isArray(rows) ? rows.map((row) => typeof row === 'number' ? row : row?.close ?? row?.price ?? row?.value ?? row?.adjClose).map(Number).filter(Number.isFinite) : [];
  }

  function marketContext(symbol) {
    if (marketCache.has(symbol)) return Promise.resolve(marketCache.get(symbol));
    if (marketInflight.has(symbol)) return marketInflight.get(symbol);
    const job = fetch(`/api/compare?tickers=${encodeURIComponent(symbol)}&period=5d`, { cache: 'no-store' })
      .then((r) => r.ok ? r.json() : null)
      .then((payload) => {
        if (!payload) return null;
        const stock = payload?.stocks?.[0] || {};
        const series = extractSeries(payload);
        let change = Number(stock.return);
        if (!Number.isFinite(change) && series.length > 1 && series[0] !== 0) change = (series.at(-1) / series[0] - 1) * 100;
        const result = { series, change: Number.isFinite(change) ? change : null };
        marketCache.set(symbol, result);
        return result;
      }).catch(() => null).finally(() => marketInflight.delete(symbol));
    marketInflight.set(symbol, job);
    return job;
  }

  async function hydrateMarket(section, items, seq) {
    const symbols = [...new Set(items.map((item) => item.symbol))];
    await Promise.allSettled(symbols.map(async (symbol) => {
      const result = await marketContext(symbol);
      if (seq !== loadSeq) return;
      const target = section.querySelector(`[data-news-v40-market="${CSS.escape(symbol)}"]`);
      if (!target) return;
      if (!result) {
        target.innerHTML = '<span>가격 흐름을 불러오지 못했습니다. 기사는 그대로 이용할 수 있습니다.</span>';
        return;
      }
      const pct = Number.isFinite(result.change) ? `${result.change > 0 ? '+' : ''}${result.change.toFixed(1)}%` : '';
      target.innerHTML = `${sparkline(result.series)}<strong class="${(result.change || 0) >= 0 ? 'up' : 'down'}">${esc(pct)}</strong><small>5거래일</small>`;
    }));
  }

  async function loadNews(force = false) {
    const section = ensureSection();
    if (!section) return;
    renderShell(section);
    const rows = readWatchlist();
    const seq = ++loadSeq;
    if (newsController) newsController.abort();
    newsController = new AbortController();

    if (!rows.length) {
      renderArticles(section, { items: [], groups: [], errors: [] }, rows, seq);
      return;
    }
    renderStatus(section, force ? '최신 뉴스를 다시 조회하고 있습니다.' : '관심종목 뉴스를 조회하고 있습니다.', `${rows.length}개 종목 전체를 조회 대상으로 사용합니다.`);
    try {
      const params = new URLSearchParams({ tickers: rows.map((r) => r.symbol).join(','), names: rows.map((r) => r.name || r.symbol).join('|') });
      if (force) params.set('_', Date.now().toString());
      const response = await fetch(`/api/personalized-news?${params}`, { cache: force ? 'no-store' : 'default', signal: newsController.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (seq !== loadSeq) return;
      const items = renderArticles(section, payload, rows, seq);
      hydrateMarket(section, items, seq).catch(() => {});
    } catch (error) {
      if (error?.name === 'AbortError' || seq !== loadSeq) return;
      renderStatus(section, '뉴스를 불러오지 못했습니다.', '기존 관심종목은 유지됩니다. 잠시 후 다시 시도해 주세요.');
      const grid = section.querySelector('[data-news-v40-grid]');
      if (grid) grid.innerHTML = '<button type="button" class="news-v40-retry" data-news-v40-retry>다시 시도</button>';
      grid?.querySelector('[data-news-v40-retry]')?.addEventListener('click', () => loadNews(true));
      console.warn('[news v40]', error);
    }
  }

  function boot(attempt = 0) {
    if (!ensureSection()) {
      if (attempt < 120) setTimeout(() => boot(attempt + 1), 250);
      return;
    }
    loadNews(false);
  }

  document.addEventListener('chartview:watchlist-change', () => setTimeout(() => loadNews(false), 40));
  window.addEventListener('storage', (event) => { if (event.key === WATCHLIST_KEY) loadNews(false); });
  document.addEventListener('click', (event) => { if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(() => boot(0), 80); });
  window.__reloadPersonalizedNewsV40 = loadNews;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(0), { once: true });
  else boot(0);
})();
