(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const DEFAULT_WATCHLIST = [
    { symbol: '005930.KS', name: '삼성전자' },
    { symbol: 'NVDA', name: '엔비디아' },
    { symbol: 'AAPL', name: '애플' },
  ];
  const MAX_NEWS_SYMBOLS = 12;
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
    } catch (_) {
      return DEFAULT_WATCHLIST;
    }
  }

  function ensureSection() {
    let section = document.getElementById('home-personal-news-v37');
    if (section) return section;
    const watchlist = document.getElementById('home-watchlist-v30');
    const body = document.getElementById('home-v8-body');
    if (!watchlist && !body) return null;
    section = document.createElement('section');
    section.id = 'home-personal-news-v37';
    section.className = 'home-v8-block home-personal-news-v37';
    section.innerHTML = `
      <div class="home-block-head news-v37-head">
        <div><span>MY NEWS · WATCHLIST</span><h3>관심종목 주요 뉴스</h3></div>
        <button type="button" data-news-v37-refresh aria-label="관심종목 뉴스 새로고침">↻ 새로고침</button>
      </div>
      <div class="news-v37-status" data-news-v37-status>관심종목 뉴스를 준비하고 있습니다.</div>
      <div class="news-v37-list" data-news-v37-list></div>
      <p class="news-v37-policy">기사 제목·출처·게시시각만 표시하며, 원문은 각 언론사 페이지에서 확인합니다.</p>`;
    if (watchlist) watchlist.insertAdjacentElement('afterend', section);
    else body.insertAdjacentElement('beforebegin', section);
    section.querySelector('[data-news-v37-refresh]')?.addEventListener('click', () => loadNews(true));
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

  function renderEmpty(section, message, detail = '') {
    const status = section.querySelector('[data-news-v37-status]');
    const list = section.querySelector('[data-news-v37-list]');
    if (status) status.innerHTML = `<strong>${esc(message)}</strong>${detail ? `<span>${esc(detail)}</span>` : ''}`;
    if (list) list.innerHTML = '';
  }

  function render(payload, rows) {
    const section = ensureSection();
    if (!section) return;
    const status = section.querySelector('[data-news-v37-status]');
    const list = section.querySelector('[data-news-v37-list]');
    const items = Array.isArray(payload?.items) ? payload.items.slice(0, 8) : [];
    const errors = Array.isArray(payload?.errors) ? payload.errors : [];

    if (!rows.length) {
      renderEmpty(section, '관심종목을 추가하면 맞춤 뉴스가 표시됩니다.', '관심종목 탭에서 종목을 추가해 보세요.');
      return;
    }
    if (!items.length) {
      const notConfigured = errors.some((x) => x?.code === 'not_configured');
      renderEmpty(
        section,
        notConfigured ? '뉴스 소스 연결을 마무리하는 중입니다.' : '최근 주요 뉴스가 없습니다.',
        notConfigured ? 'NAVER API HUB / Finnhub 키가 연결되면 자동으로 활성화됩니다.' : '새 기사가 확인되면 이 영역에 표시됩니다.'
      );
      return;
    }

    if (status) {
      const markets = new Set(items.map((x) => x.market));
      const sourceLabel = markets.size > 1 ? '한국 + 미국' : markets.has('KR') ? '한국' : '미국';
      status.innerHTML = `<strong>${esc(rows.length)}개 관심종목에서 중요 뉴스 ${esc(items.length)}건</strong><span>${sourceLabel} · 중복 기사 제거 · 최신/이벤트 중요도 순</span>`;
    }
    if (list) {
      list.innerHTML = items.map((item, index) => {
        const important = Number(item.score || 0) >= 140;
        return `<a class="news-v37-item" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" data-news-symbol="${esc(item.symbol)}">
          <div class="news-v37-item-top">
            <span class="news-v37-symbol">${esc(item.name || item.symbol)}</span>
            ${important || index < 2 ? '<b class="news-v37-highlight">주요</b>' : ''}
          </div>
          <strong class="news-v37-title">${esc(item.title)}</strong>
          <div class="news-v37-meta"><span>${esc(item.source || '원문')}</span><i>·</i><span>${esc(relativeTime(item.publishedAt))}</span><em>원문 보기 →</em></div>
        </a>`;
      }).join('');
    }
    document.dispatchEvent(new CustomEvent('chartview:v37-news-rendered'));
  }

  async function loadNews(force = false) {
    const section = ensureSection();
    if (!section) return;
    const rows = readWatchlist();
    if (!rows.length) return render({ items: [], errors: [] }, rows);
    const status = section.querySelector('[data-news-v37-status]');
    if (status) status.innerHTML = `<strong>${force ? '최신 뉴스를 다시 확인하고 있습니다.' : '관심종목 뉴스를 불러오고 있습니다.'}</strong><span>기사 원문은 저장하지 않습니다.</span>`;

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
      render(payload, rows);
    } catch (error) {
      if (seq !== loadSeq) return;
      renderEmpty(section, '뉴스를 불러오지 못했습니다.', '잠시 후 새로고침해 주세요.');
      console.warn('[V37 news] load failed', error);
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
  window.addEventListener('storage', (event) => {
    if (event.key === WATCHLIST_KEY) setTimeout(() => loadNews(false), 80);
  });
  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(() => boot(0), 80);
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(0), { once: true });
  else boot(0);

  window.__reloadPersonalizedNewsV37 = loadNews;
})();
