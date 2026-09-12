(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const SELECTED_KEY = 'chartview-selected-tickers-v1';
  const NAME_KEY = 'chartview-ticker-names-v1';
  const DETAIL_ID = 'stock-detail-v36';
  let detailSeq = 0;
  let pendingStorageReload = false;

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const asNum = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const pct = (value, digits = 2) => {
    const n = asNum(value);
    return n === null ? '-' : `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
  };
  const multiple = (value) => {
    const n = asNum(value);
    return n === null ? '-' : `${n.toFixed(1)}x`;
  };

  function storedArray(key) {
    try {
      const raw = localStorage.getItem(key);
      const value = raw ? JSON.parse(raw) : [];
      return Array.isArray(value) ? value : [];
    } catch (_) { return []; }
  }

  function tickerName(symbol, fallback) {
    try {
      const names = JSON.parse(localStorage.getItem(NAME_KEY) || '{}');
      if (names && names[symbol]) return names[symbol];
    } catch (_) { }
    return fallback || symbol;
  }

  function markExampleWatchlist() {
    const isFirstVisit = localStorage.getItem(WATCHLIST_KEY) === null;
    document.querySelectorAll('[data-v36-example-note]').forEach((node) => node.remove());
    if (!isFirstVisit) return;
    const targets = [
      document.querySelector('#home-watchlist-v30 .home-block-head'),
      document.querySelector('#watchlist-tab .watchlist-v30-head'),
    ].filter(Boolean);
    targets.forEach((target) => {
      const note = document.createElement('p');
      note.dataset.v36ExampleNote = '1';
      note.className = 'v36-example-note';
      note.textContent = '처음 방문한 브라우저에 보이는 예시 관심종목입니다. 추가·삭제 후에는 이 브라우저에 그대로 저장됩니다.';
      target.insertAdjacentElement('afterend', note);
    });
  }

  function updateWatchlistFreshnessCopy() {
    const label = document.querySelector('[data-watch-updated]');
    if (!label) return;
    const raw = label.textContent || '';
    if (/^\d{2}:\d{2}\s+(갱신|캐시)$/.test(raw)) {
      label.textContent = raw.replace(/\s+갱신$/, ' 조회').replace(/\s+캐시$/, ' 이전 조회');
      label.title = '표시 시각은 이 브라우저가 시세를 조회한 시각이며 거래 기준 시각과 다를 수 있습니다.';
    }
  }

  function ensureDetailSection() {
    let section = document.getElementById(DETAIL_ID);
    if (section) return section;
    section = document.createElement('section');
    section.id = DETAIL_ID;
    section.className = 'stock-detail-v36';
    section.hidden = true;
    const brief = document.getElementById('stock-brief-v8');
    const chartTab = document.getElementById('chart-tab');
    if (brief) brief.insertAdjacentElement('beforebegin', section);
    else if (chartTab) chartTab.insertBefore(section, chartTab.firstChild);
    return section;
  }

  function displayPrice(symbol, value) {
    const n = asNum(value);
    if (n === null) return '-';
    return /\.(KS|KQ)$/.test(symbol)
      ? `₩${Math.round(n).toLocaleString('ko-KR')}`
      : `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function basisRows(stock) {
    const meta = stock?.meta || stock?.basis || {};
    const start = stock?.actualStart || stock?.startDate || meta?.actualStart || meta?.start || '';
    const end = stock?.actualEnd || stock?.endDate || meta?.actualEnd || meta?.end || '';
    const count = stock?.observations ?? stock?.observationCount ?? meta?.observations ?? (Array.isArray(stock?.data) ? stock.data.length : null);
    const basis = stock?.priceBasis || meta?.priceBasis || stock?.basisLabel || '';
    return { start, end, count, basis };
  }

  function epsRevision(consensus) {
    const period = consensus?.periods?.['0y'] || consensus?.quote?.periods?.['0y'] || {};
    const trend = period.epsTrend || {};
    const current = asNum(trend.current ?? period?.earnings?.avg);
    const prior = asNum(trend['30daysAgo']);
    if (current === null || prior === null || current <= 0 || prior <= 0) return null;
    return (current / prior - 1) * 100;
  }

  function renderDetailLoading(section, symbol, name) {
    section.hidden = false;
    section.innerHTML = `
      <div class="v36-detail-head">
        <div><span>단일 종목 상세 · 비교목록과 별도</span><h2>${esc(name)}</h2><small>${esc(symbol)}</small></div>
      </div>
      <div class="v36-detail-loading" role="status">종목 정보를 불러오는 중...</div>`;
  }

  function renderDetail(section, symbol, name, compare, valuation, consensus) {
    const stock = compare?.stocks?.[0] || null;
    const value = valuation?.stocks?.[0] || valuation?.quotes?.[symbol] || null;
    const basis = basisRows(stock);
    const eps30 = epsRevision(consensus);
    const selected = storedArray(SELECTED_KEY).map((x) => String(x).toUpperCase());
    const alreadySelected = selected.includes(symbol);
    const atLimit = !alreadySelected && selected.length >= 6;
    const watched = typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(symbol);
    const range = basis.start && basis.end ? `${basis.start} ~ ${basis.end}` : '실제 비교 구간 확인 불가';
    const basisText = basis.basis || 'API 제공 가격 기준';
    const observationText = basis.count == null ? '-' : String(basis.count);

    section.innerHTML = `
      <div class="v36-detail-head">
        <div><span>단일 종목 상세 · 비교목록과 별도</span><h2>${esc(name)}</h2><small>${esc(symbol)}</small></div>
        <strong>${displayPrice(symbol, stock?.price ?? value?.price)}</strong>
      </div>
      <div class="v36-detail-metrics">
        <div><span>1달 수익률</span><strong>${pct(stock?.return)}</strong></div>
        <div><span>FWD PER</span><strong>${multiple(value?.forwardPE)}</strong></div>
        <div><span>EPS 컨센서스 30일</span><strong>${eps30 === null ? '-' : pct(eps30, 1)}</strong></div>
      </div>
      <div class="v36-detail-basis" aria-label="데이터 기준">
        <span><b>실제 비교 구간</b>${esc(range)}</span>
        <span><b>관측 수</b>${esc(observationText)}</span>
        <span><b>가격 기준</b>${esc(basisText)}</span>
      </div>
      <p class="v36-detail-note">이 화면을 여는 것만으로 기존 비교 종목은 추가·삭제되지 않습니다. 기간 표시는 API가 제공한 실제 관측값 기준이며, 시장 휴장일·신규 상장 등에 따라 종목별로 다를 수 있습니다.</p>
      <div class="v36-detail-actions">
        <button type="button" data-v36-compare ${alreadySelected || atLimit ? 'disabled' : ''}>${alreadySelected ? '이미 비교 중' : atLimit ? '비교 6개 사용 중' : '비교에 추가'}</button>
        <button type="button" data-v36-watch>${watched ? '★ 관심종목 해제' : '☆ 관심종목 추가'}</button>
        <button type="button" data-v36-close>상세 닫기</button>
      </div>`;

    section.querySelector('[data-v36-compare]')?.addEventListener('click', () => {
      if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
      if (typeof window.__focusStockBrief === 'function') setTimeout(() => window.__focusStockBrief(symbol), 50);
      renderDetail(section, symbol, name, compare, valuation, consensus);
    });
    section.querySelector('[data-v36-watch]')?.addEventListener('click', () => {
      if (typeof window.__toggleWatchlist === 'function') window.__toggleWatchlist(symbol, name);
      setTimeout(() => renderDetail(section, symbol, name, compare, valuation, consensus), 0);
    });
    section.querySelector('[data-v36-close]')?.addEventListener('click', () => { section.hidden = true; });
  }

  async function openDetail(symbol, name) {
    symbol = String(symbol || '').trim().toUpperCase();
    if (!symbol) return;
    name = tickerName(symbol, name);
    if (typeof window.__recordRecentTicker === 'function') window.__recordRecentTicker(symbol, name);
    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
    else if (typeof window.switchTab === 'function') window.switchTab('chart');

    const section = ensureDetailSection();
    if (!section) return;
    const seq = ++detailSeq;
    renderDetailLoading(section, symbol, name);
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });

    const requests = [
      fetch(`/api/compare?tickers=${encodeURIComponent(symbol)}&period=1mo`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
      fetch(`/api/valuation?tickers=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
      fetch(`/api/consensus?ticker=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
    ];
    const [compareResult, valuationResult, consensusResult] = await Promise.allSettled(requests);
    if (seq !== detailSeq) return;
    const compare = compareResult.status === 'fulfilled' ? compareResult.value : null;
    const valuation = valuationResult.status === 'fulfilled' ? valuationResult.value : null;
    const consensus = consensusResult.status === 'fulfilled' ? consensusResult.value : null;
    if (!compare && !valuation && !consensus) {
      section.innerHTML = '<div class="v36-detail-error" role="status">종목 상세 데이터를 불러오지 못했습니다. 기존 차트와 다른 화면은 계속 사용할 수 있습니다.</div>';
      return;
    }
    renderDetail(section, symbol, name, compare, valuation, consensus);
  }

  function interceptDetailNavigation(event) {
    const node = event.target.closest('[data-home-symbol], [data-home-watch-open], [data-watch-open], [data-watch-recent]');
    if (!node || node.closest(`#${DETAIL_ID}`)) return;
    const symbol = node.dataset.homeSymbol || node.dataset.homeWatchOpen || node.dataset.watchOpen || node.dataset.watchRecent;
    if (!symbol) return;
    const name = node.dataset.homeName || node.dataset.homeWatchName || node.dataset.watchOpenName || node.dataset.watchRecentName || symbol;
    event.preventDefault();
    event.stopImmediatePropagation();
    openDetail(symbol, name).catch((error) => console.warn('single stock detail failed', error));
  }

  function handleStorage(event) {
    if (![WATCHLIST_KEY, SELECTED_KEY, NAME_KEY].includes(event.key)) return;
    if (document.visibilityState === 'visible') {
      location.reload();
    } else {
      pendingStorageReload = true;
    }
  }

  function observeLabels() {
    const observer = new MutationObserver(() => {
      markExampleWatchlist();
      updateWatchlistFreshnessCopy();
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    setTimeout(() => observer.disconnect(), 12000);
  }

  function init() {
    ensureDetailSection();
    markExampleWatchlist();
    updateWatchlistFreshnessCopy();
    observeLabels();
    document.addEventListener('click', interceptDetailNavigation, true);
    document.addEventListener('chartview:watchlist-change', () => setTimeout(markExampleWatchlist, 0));
    window.addEventListener('storage', handleStorage);
    document.addEventListener('visibilitychange', () => {
      if (pendingStorageReload && document.visibilityState === 'visible') location.reload();
    });
    window.__openStockDetail = openDetail;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
