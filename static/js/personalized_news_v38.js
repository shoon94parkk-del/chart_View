(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const DEFAULT_WATCHLIST = [
    { symbol: '005930.KS', name: '삼성전자' },
    { symbol: 'NVDA', name: '엔비디아' },
    { symbol: 'AAPL', name: '애플' },
  ];
  const MAX_NEWS_SYMBOLS = 12;
  const TOP_COUNT = 3;
  let loadSeq = 0;

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function readWatchlist() {
    try {
      const raw = localStorage.getItem(WATCHLIST_KEY);
      const rows = raw ? JSON.parse(raw) : DEFAULT_WATCHLIST;
      if (!Array.isArray(rows)) return DEFAULT_WATCHLIST;
      const seen = new Set();
      return rows.map((row) => ({
        symbol: String(row?.symbol || row?.ticker || '').trim().toUpperCase(),
        name: String(row?.name || row?.symbol || row?.ticker || '').trim(),
      })).filter((row) => row.symbol && !seen.has(row.symbol) && seen.add(row.symbol)).slice(0, MAX_NEWS_SYMBOLS);
    } catch (_) { return DEFAULT_WATCHLIST; }
  }

  function ensureSection() {
    let section = document.getElementById('home-personal-news-v37');
    if (section) {
      section.classList.add('home-personal-news-v38');
      return section;
    }
    const watchlist = document.getElementById('home-watchlist-v30');
    const body = document.getElementById('home-v8-body');
    if (!watchlist && !body) return null;
    section = document.createElement('section');
    section.id = 'home-personal-news-v37';
    section.className = 'home-v8-block home-personal-news-v38';
    if (watchlist) watchlist.insertAdjacentElement('afterend', section);
    else body.insertAdjacentElement('beforebegin', section);
    document.dispatchEvent(new CustomEvent('chartview:v37-news-rendered'));
    return section;
  }

  function relativeTime(value) {
    if (!value) return '';
    const ts = Date.parse(value);
    if (!Number.isFinite(ts)) return '';
    const min = Math.max(0, Math.floor((Date.now() - ts) / 60000));
    if (min < 60) return `${Math.max(1, min)}분 전`;
    const hours = Math.floor(min / 60);
    if (hours < 24) return `${hours}시간 전`;
    const days = Math.floor(hours / 24);
    if (days <= 6) return `${days}일 전`;
    try { return new Date(ts).toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' }); }
    catch (_) { return ''; }
  }

  function impactScore(item) {
    const raw = Number(item?.score || 0);
    // V37 internal score commonly lands around 80~190. Normalize without pretending it is a probability.
    return Math.max(1, Math.min(100, Math.round((raw - 40) / 1.45)));
  }

  function impactMeta(score) {
    if (score >= 85) return { label: '매우 중요', level: 'critical', icon: '🔥' };
    if (score >= 70) return { label: '중요', level: 'high', icon: '▲' };
    if (score >= 50) return { label: '주목', level: 'medium', icon: '●' };
    return { label: '참고', level: 'low', icon: '○' };
  }

  function whyImportant(item) {
    const title = String(item?.title || '').toLowerCase();
    const rules = [
      [/실적|영업이익|매출|earnings|revenue|guidance/, '실적·가이던스 변화가 기업가치 기대에 직접 영향을 줄 수 있습니다.'],
      [/수주|계약|공급|contract|deal|order/, '수주·계약 변화가 향후 매출 가시성에 영향을 줄 수 있습니다.'],
      [/인수|합병|acqui|merger/, '인수합병 이벤트로 사업 구조와 가치평가 변화 가능성이 있습니다.'],
      [/배당|자사주|buyback|dividend/, '주주환원 정책 변화가 수급과 투자심리에 영향을 줄 수 있습니다.'],
      [/승인|fda|규제|sec|소송|lawsuit|리콜|recall/, '규제·법적 이벤트로 실적 또는 밸류에이션 변동성이 커질 수 있습니다.'],
      [/목표가|투자의견|upgrade|downgrade|forecast/, '시장 기대치와 밸류에이션 기준이 바뀔 수 있는 이벤트입니다.'],
    ];
    for (const [pattern, text] of rules) if (pattern.test(title)) return text;
    return '관심종목과 직접 관련된 최신 기사이며, 중요도와 최신성을 함께 반영해 선별했습니다.';
  }

  function sparklineSvg(values) {
    if (!Array.isArray(values) || values.length < 3) return '';
    const nums = values.map(Number).filter(Number.isFinite).slice(-20);
    if (nums.length < 3) return '';
    const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
    const width = 120, height = 34, pad = 2;
    const points = nums.map((v, i) => {
      const x = pad + (i / (nums.length - 1)) * (width - pad * 2);
      const y = height - pad - ((v - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg class="news-v38-spark" viewBox="0 0 ${width} ${height}" aria-label="최근 가격 흐름"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function extractSeries(payload) {
    const stock = payload?.stocks?.[0] || null;
    const candidates = [stock?.data, stock?.series, stock?.prices, payload?.data];
    for (const arr of candidates) {
      if (!Array.isArray(arr)) continue;
      const values = arr.map((row) => {
        if (typeof row === 'number') return row;
        if (!row || typeof row !== 'object') return null;
        return row.close ?? row.price ?? row.value ?? row.adjClose ?? null;
      }).map(Number).filter(Number.isFinite);
      if (values.length >= 3) return values;
    }
    return [];
  }

  async function fetchMarketContext(symbol) {
    try {
      const r = await fetch(`/api/compare?tickers=${encodeURIComponent(symbol)}&period=5d`, { cache: 'no-store' });
      if (!r.ok) return null;
      const payload = await r.json();
      const stock = payload?.stocks?.[0] || null;
      const series = extractSeries(payload);
      let change = Number(stock?.return);
      if (!Number.isFinite(change) && series.length >= 2 && series[0] !== 0) change = (series.at(-1) / series[0] - 1) * 100;
      return { series, change: Number.isFinite(change) ? change : null };
    } catch (_) { return null; }
  }

  function fmtPct(value) {
    const n = Number(value);
    return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${n.toFixed(1)}%` : '';
  }

  function renderShell(section) {
    section.innerHTML = `
      <div class="home-block-head news-v38-head">
        <div><span>MY NEWS · IMPACT</span><h3>관심종목 핵심 뉴스</h3></div>
        <button type="button" data-news-v38-refresh aria-label="관심종목 뉴스 새로고침">↻ 새로고침</button>
      </div>
      <div class="news-v38-status" data-news-v38-status>중요 뉴스를 선별하고 있습니다.</div>
      <div class="news-v38-grid" data-news-v38-grid></div>
      <div class="news-v38-foot"><span>Impact Score는 최신성·이벤트 중요도·종목 직접성을 합친 상대 점수입니다.</span><span>기사 본문·이미지는 재게시하지 않고 원문으로 연결합니다.</span></div>`;
    section.querySelector('[data-news-v38-refresh]')?.addEventListener('click', () => loadNews(true));
  }

  function renderEmpty(section, title, detail) {
    const status = section.querySelector('[data-news-v38-status]');
    const grid = section.querySelector('[data-news-v38-grid]');
    if (status) status.innerHTML = `<strong>${esc(title)}</strong>${detail ? `<span>${esc(detail)}</span>` : ''}`;
    if (grid) grid.innerHTML = '';
  }

  async function render(payload, rows) {
    const section = ensureSection();
    if (!section) return;
    renderShell(section);
    const status = section.querySelector('[data-news-v38-status]');
    const grid = section.querySelector('[data-news-v38-grid]');
    const errors = Array.isArray(payload?.errors) ? payload.errors : [];
    const items = Array.isArray(payload?.items) ? payload.items.slice(0, TOP_COUNT) : [];

    if (!rows.length) return renderEmpty(section, '관심종목을 추가하면 핵심 뉴스가 표시됩니다.', '관심종목 탭에서 종목을 추가해 보세요.');
    if (!items.length) {
      const nc = errors.some((x) => x?.code === 'not_configured');
      return renderEmpty(section, nc ? '뉴스 API 연결을 확인해 주세요.' : '최근 핵심 뉴스가 없습니다.', nc ? 'NAVER API HUB / Finnhub 환경변수를 확인해 주세요.' : '새 기사가 확인되면 이 영역에 표시됩니다.');
    }

    const contexts = await Promise.all(items.map((item) => fetchMarketContext(item.symbol)));
    if (status) status.innerHTML = `<strong>${esc(rows.length)}개 관심종목 · TOP ${esc(items.length)}</strong><span>최신성 + 이벤트 + 종목 직접성 기준으로 정렬</span>`;

    if (grid) grid.innerHTML = items.map((item, index) => {
      const score = impactScore(item);
      const meta = impactMeta(score);
      const ctx = contexts[index];
      const chart = sparklineSvg(ctx?.series || []);
      const pct = fmtPct(ctx?.change);
      return `<article class="news-v38-card ${index === 0 ? 'is-lead' : ''}" data-impact="${meta.level}">
        <div class="news-v38-card-top">
          <div class="news-v38-stock"><b>${esc(item.name || item.symbol)}</b><span>${esc(item.symbol)}</span></div>
          <div class="news-v38-impact"><strong>${meta.icon} ${score}</strong><span>${meta.label}</span></div>
        </div>
        <h4>${esc(item.title)}</h4>
        <p class="news-v38-why"><b>왜 중요?</b>${esc(whyImportant(item))}</p>
        ${chart || pct ? `<div class="news-v38-market">${chart}<div><span>최근 5일 흐름</span>${pct ? `<strong class="${Number(ctx?.change) >= 0 ? 'up' : 'down'}">${esc(pct)}</strong>` : ''}</div></div>` : ''}
        <div class="news-v38-meta"><span>${esc(item.source || '원문')}</span><i>·</i><span>${esc(relativeTime(item.publishedAt))}</span></div>
        <div class="news-v38-actions">
          <button type="button" data-news-v38-chart="${esc(item.symbol)}" data-news-v38-name="${esc(item.name || item.symbol)}">차트에서 보기</button>
          <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">원문 보기 →</a>
        </div>
      </article>`;
    }).join('');

    grid.querySelectorAll('[data-news-v38-chart]').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.newsV38Chart;
        const name = button.dataset.newsV38Name || symbol;
        if (typeof window.__openStockDetail === 'function') window.__openStockDetail(symbol, name);
      });
    });
    document.dispatchEvent(new CustomEvent('chartview:v37-news-rendered'));
  }

  async function loadNews(force = false) {
    const section = ensureSection();
    if (!section) return;
    renderShell(section);
    const rows = readWatchlist();
    if (!rows.length) return render({ items: [], errors: [] }, rows);
    const status = section.querySelector('[data-news-v38-status]');
    if (status) status.innerHTML = `<strong>${force ? '최신 뉴스를 다시 평가하고 있습니다.' : '핵심 뉴스를 선별하고 있습니다.'}</strong><span>중복 제거 후 중요도 순으로 정렬합니다.</span>`;
    const seq = ++loadSeq;
    try {
      const params = new URLSearchParams({
        tickers: rows.map((row) => row.symbol).join(','),
        names: rows.map((row) => row.name || row.symbol).join('|'),
      });
      if (force) params.set('_', String(Date.now()));
      const response = await fetch(`/api/personalized-news?${params.toString()}`, { cache: force ? 'no-store' : 'default' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (seq !== loadSeq) return;
      await render(payload, rows);
    } catch (error) {
      if (seq !== loadSeq) return;
      renderEmpty(section, '뉴스를 불러오지 못했습니다.', '잠시 후 새로고침해 주세요.');
      console.warn('[V38 news] load failed', error);
    }
  }

  function boot(attempt = 0) {
    if (!ensureSection()) {
      if (attempt < 120) setTimeout(() => boot(attempt + 1), 500);
      return;
    }
    loadNews(false);
  }

  document.addEventListener('chartview:watchlist-change', () => setTimeout(() => loadNews(false), 80));
  window.addEventListener('storage', (event) => { if (event.key === WATCHLIST_KEY) setTimeout(() => loadNews(false), 80); });
  document.addEventListener('click', (event) => { if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(() => boot(0), 80); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(0), { once: true });
  else boot(0);
  window.__reloadPersonalizedNewsV38 = loadNews;
})();
