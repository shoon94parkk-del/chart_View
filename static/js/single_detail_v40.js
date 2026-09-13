(() => {
  'use strict';

  if (window.__chartViewDetailV40Installed) return;
  window.__chartViewDetailV40Installed = true;

  const DETAIL_ID = 'stock-detail-v40';
  let controller = null;
  let lastOrigin = null;

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const D = () => window.ChartViewData;
  const S = () => window.ChartViewState;
  const marketLabel = (symbol) => /\.(KS|KQ)$/.test(symbol) ? 'KR' : 'US';
  const shortDate = (value) => {
    const match = String(value || '').match(/(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[2]}.${match[3]}` : '기준일 확인 필요';
  };

  function ensureSection() {
    let section = document.getElementById(DETAIL_ID);
    if (section) return section;
    section = document.createElement('section');
    section.id = DETAIL_ID;
    section.className = 'stock-detail-v40';
    section.hidden = true;
    const chartTab = document.getElementById('chart-tab');
    const brief = document.getElementById('stock-brief-v8');
    if (brief) brief.insertAdjacentElement('beforebegin', section);
    else if (chartTab) chartTab.prepend(section);
    return section;
  }

  function selectedCompare() {
    return S()?.getCompare?.().items || [];
  }

  function comparisonState(symbol) {
    const rows = selectedCompare();
    if (rows.includes(symbol)) return { key: 'included', label: '비교 중', disabled: true };
    if (rows.length >= 6) return { key: 'full', label: '비교목록 관리', disabled: false };
    return { key: 'add', label: '비교에 추가', disabled: false };
  }

  function renderLoading(section, symbol, name) {
    section.hidden = false;
    document.body.classList.add('app-detail-v40-open');
    section.innerHTML = `
      <div class="detail-v40-shell" aria-busy="true">
        <header class="detail-v40-header">
          <button type="button" class="detail-v40-back" data-detail-back aria-label="이전 화면으로 돌아가기">←</button>
          <div class="detail-v40-id"><strong>${esc(name)}</strong><span>${esc(symbol)} · ${marketLabel(symbol)}</span></div>
        </header>
        <div class="detail-v40-loading" role="status"><span class="ux-mini-spinner"></span>종목 상세를 불러오는 중…</div>
      </div>`;
    bindBack(section);
  }

  function extractSeries(stock) {
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

  function metric(label, value, sub = '') {
    return `<div class="detail-v40-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
  }

  function basisText(stock) {
    const start = stock?.actualStart || stock?.startDate || stock?.meta?.actualStart || stock?.meta?.start || '';
    const end = stock?.actualEnd || stock?.endDate || stock?.meta?.actualEnd || stock?.meta?.end || '';
    const priceBasis = stock?.priceBasis || stock?.meta?.priceBasis || stock?.basisLabel || 'API 제공 가격 기준';
    return { start, end, priceBasis };
  }

  function revisionState(consensus) {
    const period = consensus?.periods?.['0y'] || consensus?.quote?.periods?.['0y'] || {};
    const trend = period?.epsTrend || {};
    return D()?.calcRevision?.(trend.current ?? period?.earnings?.avg, trend['30daysAgo']) || { kind: 'missing', value: null };
  }

  function valueRow(label, value, basis, options = {}) {
    return `<div class="detail-v40-value-row">
      <div><span>${esc(label)}</span><strong>${esc(value)}</strong>${options.badge ? `<em>${esc(options.badge)}</em>` : ''}</div>
      <details><summary>기준 보기</summary><p>${esc(basis || '원자료 기준을 확인할 수 없습니다.')}</p></details>
    </div>`;
  }

  function valueBasis(stock, key, fallback) {
    const meta = stock?.fieldMeta?.[key];
    if (meta) {
      const parts = [meta.asOf, meta.period, meta.source, meta.method && meta.method !== 'provider' ? meta.method : ''].filter(Boolean);
      if (parts.length) return parts.join(' · ');
    }
    return fallback;
  }

  function renderDetail(section, symbol, name, comparePayload, valuationPayload, consensusPayload) {
    if (!S()?.detail?.open || S().detail.symbol !== symbol) return;
    const stock = comparePayload?.stocks?.[0] || {};
    const value = valuationPayload?.stocks?.[0] || valuationPayload?.quotes?.[symbol] || {};
    const rev = revisionState(consensusPayload);
    const basis = basisText(stock);
    const compare = comparisonState(symbol);
    const watched = typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(symbol);
    const price = D()?.formatPrice?.(symbol, stock?.price ?? value?.price) || '—';
    const ret = D()?.formatPercent?.(stock?.return, 2) || '—';
    const fwd = D()?.formatMultiple?.(value?.forwardPE, 1) || '—';
    const eps = rev.kind === 'number' ? D().formatPercent(rev.value, 1) : rev.kind === 'unavailable' ? '계산 불가' : '—';
    const series = extractSeries(stock);
    const tradeDate = basis.end || stock?.asOf || '';
    const roe = D()?.formatPercent?.(value?.roe, 2) || '—';
    const dividend = D()?.formatPercent?.(value?.dividendYield, 2) || '—';
    const trailing = D()?.formatMultiple?.(value?.trailingPE, 1) || '—';
    const pbr = D()?.formatMultiple?.(value?.pbr, 1) || '—';
    const psr = D()?.formatMultiple?.(value?.psr, 1) || '—';
    const ev = D()?.formatMultiple?.(value?.evEbitda, 1) || '—';

    section.hidden = false;
    section.innerHTML = `
      <div class="detail-v40-shell">
        <header class="detail-v40-header">
          <button type="button" class="detail-v40-back" data-detail-back aria-label="이전 화면으로 돌아가기">←</button>
          <div class="detail-v40-id"><strong>${esc(name)}</strong><span>${esc(symbol)} · ${marketLabel(symbol)}</span></div>
          <div class="detail-v40-actions">
            <button type="button" data-detail-watch>${watched ? '★ 관심' : '☆ 관심'}</button>
            <button type="button" data-detail-compare data-state="${compare.key}" ${compare.disabled ? 'disabled' : ''}>${compare.label}</button>
          </div>
        </header>
        <section class="detail-v40-price" aria-label="현재 가격">
          <div><span>현재가</span><strong>${esc(price)}</strong></div>
          <small>${esc(shortDate(tradeDate))} 거래 기준 · 브라우저 조회 ${new Intl.DateTimeFormat('ko-KR', { hour:'2-digit', minute:'2-digit', hour12:false }).format(new Date())}</small>
        </section>
        <div class="detail-v40-metrics">
          ${metric('1달 수익률', ret, basis.start && basis.end ? `${shortDate(basis.start)}~${shortDate(basis.end)}` : '실제 관측 구간')}
          ${metric('FWD PER', fwd, '예상 기간 미확인')}
          ${metric('EPS 전망 30일', eps, rev.kind === 'unavailable' ? '분모 0 등 계산 불가' : '컨센서스 변화')}
        </div>
        <nav class="detail-v40-tabs" aria-label="단일 종목 상세 영역">
          <button type="button" class="active" data-detail-tab="chart">차트</button>
          <button type="button" data-detail-tab="value">재무·밸류</button>
          <button type="button" data-detail-tab="decision">투자판단</button>
        </nav>
        <section class="detail-v40-panel active" data-detail-panel="chart">
          <div class="detail-v40-panel-head"><div><strong>1달 수익률 차트</strong><span>가격 자체가 아니라 기간 시작 대비 수익률 흐름입니다.</span></div><span>1달</span></div>
          <div class="detail-v40-chart">${sparkline(series)}</div>
          <div class="detail-v40-basis"><span>관측 ${esc(basis.start || '—')} ~ ${esc(basis.end || '—')}</span><span>가격 기준 ${esc(basis.priceBasis)}</span></div>
        </section>
        <section class="detail-v40-panel" data-detail-panel="value" hidden>
          <div class="detail-v40-value-list">
            ${valueRow('FWD PER', fwd, valueBasis(value, 'forwardPE', '예상 기간 미확인 · 제공처 기준'), { badge: '예상 기간 미확인' })}
            ${valueRow('PER', trailing, valueBasis(value, 'trailingPE', 'TTM/최근 실적 기준'))}
            ${valueRow('ROE', roe, valueBasis(value, 'roe', 'API 제공 ROE 단위 그대로 표시'))}
            ${valueRow('PBR', pbr, valueBasis(value, 'pbr', '최근 공시/제공처 기준'))}
            ${valueRow('PSR', psr, valueBasis(value, 'psr', 'TTM 매출 기준'))}
            ${valueRow('EV/EBITDA', ev, valueBasis(value, 'evEbitda', 'TTM/최근 공시 기준'))}
            ${valueRow('배당수익률', dividend, valueBasis(value, 'dividendYield', '최근 배당/제공처 기준'))}
          </div>
        </section>
        <section class="detail-v40-panel" data-detail-panel="decision" hidden>
          <div class="detail-v40-decision-note"><strong>투자판단 근거</strong><span>매수·매도 점수가 아니라 현재 공개 데이터에서 확인할 항목을 정리합니다.</span></div>
          <div class="detail-v40-decision-grid">
            ${metric('가격 모멘텀 · 1달', ret)}
            ${metric('EPS 전망 · 30일', eps)}
            ${metric('FWD PER', fwd, '예상 기간 미확인')}
            ${metric('ROE', roe)}
          </div>
          <p>높거나 낮은 단일 지표만으로 결론내리지 말고 업종, 자본구조, 전망 기간과 원자료 기준을 함께 확인하세요.</p>
        </section>
      </div>`;

    bindBack(section);
    bindActions(section, symbol, name);
    bindTabs(section);
  }

  function bindBack(section) {
    section.querySelector('[data-detail-back]')?.addEventListener('click', closeDetail);
  }

  function bindTabs(section) {
    section.querySelectorAll('[data-detail-tab]').forEach((button) => {
      button.addEventListener('click', () => {
        const tab = button.dataset.detailTab;
        section.querySelectorAll('[data-detail-tab]').forEach((el) => el.classList.toggle('active', el === button));
        section.querySelectorAll('[data-detail-panel]').forEach((panel) => {
          const active = panel.dataset.detailPanel === tab;
          panel.hidden = !active;
          panel.classList.toggle('active', active);
        });
      });
    });
  }

  function bindActions(section, symbol, name) {
    section.querySelector('[data-detail-watch]')?.addEventListener('click', () => {
      if (typeof window.__toggleWatchlist !== 'function') return;
      window.__toggleWatchlist(symbol, name);
      const watched = typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(symbol);
      const button = section.querySelector('[data-detail-watch]');
      if (button) button.textContent = watched ? '★ 관심' : '☆ 관심';
    });
    section.querySelector('[data-detail-compare]')?.addEventListener('click', () => {
      const state = comparisonState(symbol);
      if (state.key === 'full') {
        closeDetail({ force: true, restore: false });
        if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      if (state.key !== 'add') return;
      if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
      setTimeout(() => {
        S()?.syncLegacyCompare?.();
        const current = comparisonState(symbol);
        const button = section.querySelector('[data-detail-compare]');
        if (button) {
          button.dataset.state = current.key;
          button.textContent = current.label;
          button.disabled = current.disabled;
        }
      }, 0);
    });
  }

  async function openDetail(symbol, name, options = {}) {
    symbol = String(symbol || '').trim().toUpperCase();
    if (!symbol || !S() || !D()) return;
    name = String(name || S().getNames?.()[symbol] || symbol);

    if (controller) controller.abort();
    controller = new AbortController();
    const state = S().beginDetail(symbol, name);
    const section = ensureSection();
    if (!section) return;

    const alreadyDetail = history.state?.chartView && history.state?.view === 'detail';
    if (!alreadyDetail) {
      lastOrigin = options.origin || S().captureScreen();
      try { history.replaceState({ ...(history.state || {}), chartView: true, tab: lastOrigin.tab, screen: lastOrigin }, '', location.href); } catch (_) { }
    }
    if (typeof window.__recordRecentTicker === 'function') window.__recordRecentTicker(symbol, name);
    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart', { history: false });
    else if (typeof window.switchTab === 'function') window.switchTab('chart');
    if (options.history !== false) {
      const payload = { chartView: true, tab: 'chart', view: 'detail', symbol, name, screen: lastOrigin };
      try {
        if (alreadyDetail) history.replaceState(payload, '', location.href);
        else history.pushState(payload, '', location.href);
      } catch (_) { }
    }

    renderLoading(section, symbol, name);
    section.scrollIntoView({ block: 'start', behavior: options.instant ? 'auto' : 'smooth' });

    const request = (url) => fetch(url, { cache: 'no-store', signal: controller.signal }).then((r) => r.ok ? r.json() : null);
    const results = await Promise.allSettled([
      request(`/api/compare?tickers=${encodeURIComponent(symbol)}&period=1mo`),
      request(`/api/valuation?tickers=${encodeURIComponent(symbol)}`),
      request(`/api/consensus?ticker=${encodeURIComponent(symbol)}`),
    ]);
    if (!S().isCurrentDetail(symbol, state.seq)) return;
    const compare = results[0].status === 'fulfilled' ? results[0].value : null;
    const valuation = results[1].status === 'fulfilled' ? results[1].value : null;
    const consensus = results[2].status === 'fulfilled' ? results[2].value : null;
    if (!compare && !valuation && !consensus) {
      section.innerHTML = `<div class="detail-v40-error" role="alert"><strong>종목 상세를 불러오지 못했습니다.</strong><button type="button" data-detail-retry>다시 시도</button><button type="button" data-detail-back>돌아가기</button></div>`;
      section.querySelector('[data-detail-retry]')?.addEventListener('click', () => openDetail(symbol, name, { history: false }));
      bindBack(section);
      return;
    }
    renderDetail(section, symbol, name, compare, valuation, consensus);
  }

  function hideDetail() {
    if (controller) controller.abort();
    controller = null;
    S()?.closeDetail?.();
    const section = document.getElementById(DETAIL_ID);
    if (section) { section.hidden = true; section.replaceChildren(); }
    document.body.classList.remove('app-detail-v40-open');
  }

  function closeDetail(options = {}) {
    const currentIsDetail = history.state?.chartView && history.state?.view === 'detail';
    hideDetail();
    if (!options.force && currentIsDetail && history.length > 1) {
      history.back();
      return;
    }
    if (options.restore !== false && lastOrigin) S()?.restoreScreen?.(lastOrigin);
  }

  function detailClick(event) {
    const node = event.target.closest('[data-home-symbol], [data-home-watch-open], [data-watch-open], [data-watch-recent], .screen-idea[data-symbol], [data-news-v40-detail]');
    if (!node || node.closest(`#${DETAIL_ID}`)) return;
    const symbol = node.dataset.homeSymbol || node.dataset.homeWatchOpen || node.dataset.watchOpen || node.dataset.watchRecent || node.dataset.symbol || node.dataset.newsV40Detail;
    if (!symbol) return;
    const name = node.dataset.homeName || node.dataset.homeWatchName || node.dataset.watchOpenName || node.dataset.watchRecentName || node.dataset.name || node.dataset.newsV40Name || symbol;
    event.preventDefault();
    event.stopImmediatePropagation();
    openDetail(symbol, name).catch((error) => console.warn('[detail v40]', error));
  }

  function onPopState(event) {
    const state = event.state || {};
    if (state.chartView && state.view === 'detail' && state.symbol) {
      openDetail(state.symbol, state.name || state.symbol, { history: false, instant: true, origin: state.screen }).catch(() => {});
      return;
    }
    const wasOpen = Boolean(S()?.detail?.open);
    if (wasOpen) hideDetail();
    const screen = state.screen || lastOrigin;
    if (screen) setTimeout(() => S()?.restoreScreen?.(screen), 30);
  }

  document.addEventListener('click', detailClick, true);
  window.addEventListener('popstate', onPopState);
  window.__openStockDetail = openDetail;
  window.__closeStockDetail = closeDetail;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensureSection, { once: true });
  else ensureSection();
})();
