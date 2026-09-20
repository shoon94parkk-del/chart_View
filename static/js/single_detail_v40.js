(() => {
  'use strict';

  if (window.__chartViewDetailV40Installed) return;
  window.__chartViewDetailV40Installed = true;

  const DETAIL_ID = 'stock-detail-v40';
  let controller = null;
  let lastOrigin = null;
  let detailSession = null;
  const PERIODS = { '1mo': '1개월', '3mo': '3개월', '6mo': '6개월', ytd: 'YTD', '1y': '1년' };

  function quotePresentation(stock, value) {
    const valid = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
    const useStock = valid(stock?.price);
    return { price: useStock ? stock.price : value?.price,
      asOf: useStock ? (stock.quoteAsOf || '') : (value?.fieldMeta?.price?.asOf || ''),
      source: useStock ? (stock.quoteSource || stock.source || '') : (value?.fieldMeta?.price?.source || value?.dataSource || '') };
  }

  function displayValue(formatted, source) {
    return !formatted || formatted === '—' || formatted === '-' ? sourceStatus(source) : formatted;
  }

  function quoteTime(raw) {
    if (!raw) return '시세 시각 미확인';
    const date = new Date(raw);
    if (!Number.isFinite(date.getTime())) return '시세 시각 미확인';
    return new Intl.DateTimeFormat('ko-KR', {timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date) + ' KST';
  }

  function sourceStatus(key) {
    const status = detailSession?.status?.[key];
    if (status === 'loading') return '불러오는 중';
    if (status === 'error') return '조회 실패';
    return '미제공';
  }


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
    if (!Array.isArray(series) || series.length < 2) {
      const status = detailSession?.status?.compare;
      if (status === 'loading') return '<div class="detail-v40-chart-empty is-loading" role="status">차트를 불러오는 중…</div>';
      if (status === 'error') return '<div class="detail-v40-chart-empty is-error">차트 조회에 실패했습니다. 위의 다시 시도를 이용해 주세요.</div>';
      return '<div class="detail-v40-chart-empty">이 기간의 거래 데이터가 없습니다.</div>';
    }
    const points = series;
    const nums = points.map((row) => row.value);
    const min = Math.min(...nums), max = Math.max(...nums);
    const rawLow = min === max ? min - 1 : min, rawHigh = min === max ? max + 1 : max;
    const low = Math.min(0, rawLow), high = Math.max(0, rawHigh), span = high - low || 1;
    const width = 720, height = 220, left = 54, right = 12, top = 16, bottom = 22;
    const xy = points.map((row, index) => {
      const x = left + (index / Math.max(1, points.length - 1)) * (width - left - right);
      const y = height - bottom - ((row.value - low) / span) * (height - top - bottom);
      return { x, y };
    });
    const poly = xy.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const zeroY = low <= 0 && high >= 0 ? height - bottom - ((0 - low) / span) * (height - top - bottom) : null;
    return `<div class="detail-v42-chart-wrap" data-detail-chart tabindex="0" aria-label="${PERIODS[detailSession?.period || '1mo']} 수익률 차트. 좌우 화살표 또는 터치로 날짜별 값을 확인할 수 있습니다.">
      <div class="detail-v42-chart-readout" data-detail-chart-readout>터치하거나 좌우키로 날짜별 수익률 확인</div>
      <svg class="detail-v40-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${PERIODS[detailSession?.period || '1mo']} 수익률 흐름">
        ${zeroY === null ? '' : `<line class="detail-v42-zero" x1="${left}" x2="${width-right}" y1="${zeroY.toFixed(1)}" y2="${zeroY.toFixed(1)}"/><text class="detail-v42-zero-label" x="4" y="${Math.max(top + 10, Math.min(height - bottom - 4, zeroY - 4)).toFixed(1)}">0%</text>`}
        <text class="detail-v42-y-label" x="4" y="${top + 4}">${high.toFixed(1)}%</text>
        <text class="detail-v42-y-label" x="4" y="${height-bottom}">${low.toFixed(1)}%</text>
        <polyline points="${poly}" fill="none" stroke="currentColor" stroke-width="4" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="detail-v42-chart-axis"><span>${esc(pointDate(points[0]) || '시작')}</span><span>${esc(pointDate(points.at(-1)) || '현재')}</span></div>
    </div>`;
  }

  function bindChart(section, series) {
    const root = section.querySelector('[data-detail-chart]');
    const svg = root?.querySelector('svg');
    const readout = root?.querySelector('[data-detail-chart-readout]');
    const points = Array.isArray(series) ? series : [];
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

  function metric(label, value, sub = '') {
    return `<div class="detail-v40-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
  }

  function basisText(stock) {
    const start = stock?.actualStart || stock?.startDate || stock?.meta?.actualStart || stock?.meta?.start || '';
    const end = stock?.actualEnd || stock?.endDate || stock?.meta?.actualEnd || stock?.meta?.end || '';
    const rawBasis = stock?.priceBasis || stock?.meta?.priceBasis || stock?.basisLabel || '';
    const priceBasis = rawBasis === 'adjusted_close' ? '조정주가' : rawBasis === 'close' ? '종가' : (rawBasis || 'API 제공 가격 기준');
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
    const quote = quotePresentation(stock, value);
    const price = D()?.formatPrice?.(symbol, quote.price) || '—';
    const periodLabel = PERIODS[detailSession?.period || '1mo'];
    const activeTab = section.querySelector('[data-detail-tab].active')?.dataset.detailTab || 'chart';
    const ret = D()?.formatPercent?.(stock?.return, 2) || '—';
    const fwd = displayValue(D()?.formatMultiple?.(value?.forwardPE, 1), 'valuation');
    const eps = rev.kind === 'number' ? D().formatPercent(rev.value, 1) : rev.kind === 'unavailable' ? '계산 불가' : sourceStatus('consensus');
    const series = extractSeries(stock);
    const tradeDate = quote.asOf;
    const roe = displayValue(D()?.formatPercent?.(value?.roe, 2), 'valuation');
    const dividend = displayValue(D()?.formatPercent?.(value?.dividendYield, 2), 'valuation');
    const trailing = displayValue(D()?.formatMultiple?.(value?.trailingPE, 1), 'valuation');
    const pbr = displayValue(D()?.formatMultiple?.(value?.pbr, 1), 'valuation');
    const psr = displayValue(D()?.formatMultiple?.(value?.psr, 1), 'valuation');
    const ev = displayValue(D()?.formatMultiple?.(value?.evEbitda, 1), 'valuation');
    const fwdMeta = value?.fieldMeta?.forwardPE || {};
    const fwdPeriod = String(fwdMeta.period || '').trim() || '기간 미확인';

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
          <div><span>최근 시세</span><strong>${esc(price)}</strong></div>
          <div class="detail-quote-basis">
            <small>${esc(quoteTime(tradeDate))}</small>
            <details><summary>시세 기준</summary><p>${esc(quote.source || '출처 미확인')} · 스크리너 종가와 시점·출처가 다를 수 있음</p></details>
          </div>
        </section>
        <div class="detail-source-status" role="status">${[['compare','차트'],['valuation','재무'],['consensus','컨센서스']].map(([key,label]) => detailSession?.status[key] === 'error' ? `${label} 조회 실패 <button type="button" data-detail-retry-source="${key}">다시 시도</button>` : detailSession?.status[key] === 'loading' ? `${label} 불러오는 중…` : '').filter(Boolean).join(' · ')}</div>
        <div class="detail-v40-metrics">
          ${metric(`${periodLabel} 수익률`, ret, basis.start && basis.end ? `${shortDate(basis.start)}~${shortDate(basis.end)}` : '실제 관측 구간')}
          ${metric('예상 PER', fwd, fwdPeriod)}
          ${metric('EPS 전망 30일', eps, rev.kind === 'unavailable' ? '분모 0 등 계산 불가' : '컨센서스 변화')}
        </div>
        <nav class="detail-v40-tabs" aria-label="단일 종목 상세 영역">
          <button type="button" class="active" data-detail-tab="chart">차트</button>
          <button type="button" data-detail-tab="value">재무·밸류</button>
          <button type="button" data-detail-tab="decision">분석 요약</button>
        </nav>
        <section class="detail-v40-panel active" data-detail-panel="chart">
          <div class="detail-v40-panel-head"><div><strong>${periodLabel} 수익률 차트</strong><span>가격 자체가 아니라 기간 시작 대비 수익률 흐름입니다.</span></div><span>${periodLabel}</span></div>
          <div class="detail-periods" role="group" aria-label="상세 차트 기간">${Object.entries(PERIODS).map(([key,label]) => `<button type="button" data-detail-period="${key}" aria-pressed="${key === (detailSession?.period || '1mo')}">${label}</button>`).join('')}</div>
          <div class="detail-v40-chart">${sparkline(series)}</div>
          <div class="detail-v40-basis"><span>관측 ${esc(basis.start || '—')} ~ ${esc(basis.end || '—')}</span><span>가격 기준 ${esc(basis.priceBasis)}</span></div>
        </section>
        <section class="detail-v40-panel" data-detail-panel="value" hidden>
          <div class="detail-v40-value-list">
            ${valueRow('예상 PER', fwd, valueBasis(value, 'forwardPE', '예상 기간 미확인 · 제공처 기준'), { badge: fwdPeriod })}
            ${valueRow('PER', trailing, valueBasis(value, 'trailingPE', 'TTM/최근 실적 기준'))}
            ${valueRow('ROE', roe, valueBasis(value, 'roe', 'API 제공 ROE 단위 그대로 표시'))}
            ${valueRow('PBR', pbr, valueBasis(value, 'pbr', '최근 공시/제공처 기준'))}
            ${valueRow('PSR', psr, valueBasis(value, 'psr', 'TTM 매출 기준'))}
            ${valueRow('EV/EBITDA', ev, valueBasis(value, 'evEbitda', 'TTM/최근 공시 기준'))}
            ${valueRow('배당수익률', dividend, valueBasis(value, 'dividendYield', '최근 배당/제공처 기준'))}
          </div>
        </section>
        <section class="detail-v40-panel" data-detail-panel="decision" hidden>
          <div class="detail-v40-decision-note"><strong>분석 요약</strong><span>관찰된 사실, 비교할 기준, 추가 확인 항목을 나눠서 봅니다.</span></div>
          <div class="detail-v40-decision-sections">
            <section class="detail-v40-decision-section" aria-label="관찰된 사실">
              <h4>관찰된 사실</h4>
              <div class="detail-v40-decision-grid">
                ${metric(periodLabel + ' 수익률', ret, basis.start && basis.end ? shortDate(basis.start) + '~' + shortDate(basis.end) : '실제 관측 구간')}
                ${metric('EPS 전망 · 30일', eps, rev.kind === 'unavailable' ? '분모 0 등 계산 불가' : '컨센서스 변화')}
              </div>
            </section>
            <section class="detail-v40-decision-section" aria-label="비교할 기준">
              <h4>비교할 기준</h4>
              <div class="detail-v40-decision-grid">
                ${metric('예상 PER', fwd, fwdPeriod)}
                ${metric('ROE', roe, valueBasis(value, 'roe', '최근 제공값 기준'))}
              </div>
            </section>
            <section class="detail-v40-decision-section detail-v40-checks" aria-label="확인이 필요한 점">
              <h4>확인이 필요한 점</h4>
              <ul>
                <li><strong>예상 PER 기간</strong><span>${esc(fwdPeriod)}</span></li>
                <li><strong>예상 PER 원자료</strong><span>${esc(valueBasis(value, 'forwardPE', '제공처 기준 · 기간 미확인'))}</span></li>
                <li><strong>비교 해석</strong><span>업종·자본구조·기준일이 다른 종목과는 단순 순위 비교를 피하세요.</span></li>
              </ul>
            </section>
          </div>
        </section>
      </div>`;

    bindBack(section);
    bindActions(section, symbol, name);
    bindTabs(section);
    bindChart(section, series);
    section.querySelectorAll('[data-detail-tab]').forEach(el => el.classList.toggle('active', el.dataset.detailTab === activeTab));
    section.querySelectorAll('[data-detail-panel]').forEach(el => { el.hidden = el.dataset.detailPanel !== activeTab; el.classList.toggle('active', !el.hidden); });
    section.querySelectorAll('[data-detail-period]').forEach(button => button.addEventListener('click', () => {
      const session = detailSession;
      if (!session || session.period === button.dataset.detailPeriod) return;
      session.period = button.dataset.detailPeriod;
      session.data.compare = null;
      loadDetailSource(session, 'compare');
    }));
    section.querySelectorAll('[data-detail-retry-source]').forEach(button => button.addEventListener('click', () => loadDetailSource(detailSession, button.dataset.detailRetrySource)));

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

    detailSession = { symbol, name, seq: state.seq, section, controller, period: '1mo',
      status: {compare:'loading', valuation:'loading', consensus:'loading'}, data: {}, requests: {} };
    const session = detailSession;
    paintDetailSession(session);
    ['compare','valuation','consensus'].forEach(key => loadDetailSource(session, key));
  }

  function paintDetailSession(session) {
    if (detailSession !== session || !S().isCurrentDetail(session.symbol, session.seq)) return;
    renderDetail(session.section, session.symbol, session.name, session.data.compare, session.data.valuation, session.data.consensus);
  }

  async function loadDetailSource(session, key) {
    if (!session || detailSession !== session) return;
    session.requests[key]?.abort();
    const requestController = new AbortController();
    session.requests[key] = requestController;
    const abort = () => requestController.abort();
    session.controller.signal.addEventListener('abort', abort, {once:true});
    const timeout = setTimeout(abort, 15000);
    session.status[key] = 'loading';
    paintDetailSession(session);
    const symbol = encodeURIComponent(session.symbol);
    const url = key === 'compare' ? `/api/compare?tickers=${symbol}&period=${session.period}` : key === 'valuation' ? `/api/valuation?tickers=${symbol}` : `/api/consensus?ticker=${symbol}`;
    try {
      const response = await fetch(url, {cache:'no-store',signal:requestController.signal});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data?.error || ((key === 'compare' || key === 'valuation') && !data?.stocks?.length && !data?.quotes?.[session.symbol])) throw new Error('Provider error');
      if (session.requests[key] !== requestController || detailSession !== session || session.controller.signal.aborted) return;
      session.data[key] = data;
      session.status[key] = 'ready';
    } catch (error) {
      if (session.requests[key] !== requestController || detailSession !== session || session.controller.signal.aborted) return;
      session.status[key] = 'error';
    } finally {
      clearTimeout(timeout);
      session.controller.signal.removeEventListener('abort', abort);
      if (session.requests[key] === requestController) paintDetailSession(session);
    }
  }

  function hideDetail() {
    if (controller) controller.abort();
    controller = null;
    detailSession = null;
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
