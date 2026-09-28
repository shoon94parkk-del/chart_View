(() => {
  'use strict';

  const PAGE_SIZE = 60;
  const state = {
    rows: [],
    days: [],
    monitorPicks: [],
    monitorStatus: 'all',
    loaded: false,
    loading: false,
    visibleCount: PAGE_SIZE,
    query: '',
    period: 'all',
    performance: 'all',
    sort: 'latest',
    activeView: 'screener',
  };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const number = (value) => {
    if (value === null || value === undefined || String(value).trim() === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  const price = (value) => {
    const n = number(value);
    return n == null ? '-' : `${Math.round(n).toLocaleString('ko-KR')}원`;
  };

  const pct = (value) => {
    const n = number(value);
    if (n == null) return '-';
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  };

  const cls = (value) => {
    const n = number(value);
    return n == null ? '' : n > 0 ? 'up' : n < 0 ? 'down' : 'flat';
  };

  const dateValue = (value) => {
    const t = Date.parse(`${String(value || '')}T00:00:00+09:00`);
    return Number.isFinite(t) ? t : 0;
  };

  function shellMarkup() {
    return `
      <div class="discovery-subnav" role="tablist" aria-label="종목 발굴 보기">
        <button type="button" class="discovery-subtab active" data-discovery-view="screener" role="tab" aria-selected="true">시장 스크리너</button>
        <button type="button" class="discovery-subtab" data-discovery-view="pick-monitor" role="tab" aria-selected="false">PICK 점검</button>
        <button type="button" class="discovery-subtab" data-discovery-view="ai-picks" role="tab" aria-selected="false">AI PICK 기록</button>
      </div>
      <section class="ai-monitor-panel" data-discovery-panel="pick-monitor" hidden aria-label="기존 PICK 사후관리">
        <div class="ai-ledger-head">
          <div>
            <span class="ai-ledger-eyebrow">PICK POST-MONITOR</span>
            <h2>기존 PICK 점검</h2>
            <p>추천 당시 투자논리와 최신 검증 근거를 비교합니다. 매도검토는 자동 매도 확정이 아니며 사용자 확인이 필요합니다.</p>
          </div>
          <span class="ai-ledger-data-date" data-monitor-date>점검 데이터 불러오는 중</span>
        </div>
        <div class="ai-monitor-kpis" data-monitor-kpis aria-label="PICK 점검 상태 요약"></div>
        <div class="ai-monitor-tools">
          <select class="ai-ledger-select" data-monitor-status aria-label="PICK 상태 필터">
            <option value="all">상태 전체</option>
            <option value="SELL_REVIEW">🔴 매도검토</option>
            <option value="WATCH">🟡 경계</option>
            <option value="KEEP">🟢 유지</option>
            <option value="PENDING_REVIEW">⚪ 검토 대기</option>
            <option value="EXIT">종료</option>
          </select>
          <span class="ai-monitor-policy">가격·차트만으로 매도검토하지 않음</span>
        </div>
        <div class="ai-monitor-content" data-monitor-content>
          <div class="ai-ledger-empty">PICK 점검 데이터를 불러오는 중입니다.</div>
        </div>
      </section>
      <section class="ai-ledger-panel" data-discovery-panel="ai-picks" hidden aria-label="AI PICK 누적 기록">
        <div class="ai-ledger-head">
          <div>
            <span class="ai-ledger-eyebrow">CHARTVIEW AI PICK</span>
            <h2>누적 추천 원장</h2>
            <p>거래일별로 선정된 추천 종목을 한 화면에서 비교하고, 필요한 행만 펼쳐 추천 사유를 확인합니다.</p>
          </div>
          <span class="ai-ledger-data-date" data-ledger-date>데이터 불러오는 중</span>
        </div>
        <div class="ai-ledger-kpis" data-ledger-kpis aria-label="AI PICK 성과 요약"></div>
        <div class="ai-ledger-tools" aria-label="AI PICK 기록 필터">
          <label class="ai-ledger-search-wrap">
            <span class="sr-only">종목 검색</span>
            <input type="search" class="ai-ledger-search" data-ledger-search placeholder="종목명 · 코드 검색" autocomplete="off">
          </label>
          <select class="ai-ledger-select" data-ledger-period aria-label="기간 필터">
            <option value="all">기간 전체</option>
            <option value="7">최근 7일</option>
            <option value="30">최근 30일</option>
          </select>
          <select class="ai-ledger-select" data-ledger-performance aria-label="성과 필터">
            <option value="all">성과 전체</option>
            <option value="win">수익 종목</option>
            <option value="loss">손실 종목</option>
          </select>
          <select class="ai-ledger-select" data-ledger-sort aria-label="정렬 기준">
            <option value="latest">최신 추천순</option>
            <option value="return">수익률 높은순</option>
            <option value="best">최고수익률 높은순</option>
            <option value="score">점수 높은순</option>
          </select>
        </div>
        <div class="ai-ledger-summary" data-ledger-summary aria-live="polite"></div>
        <div class="ai-ledger-content" data-ledger-content>
          <div class="ai-ledger-empty">AI PICK 기록을 불러오는 중입니다.</div>
        </div>
        <button type="button" class="ai-ledger-more" data-ledger-more hidden>더 보기</button>
      </section>`;
  }

  function installShell(attempt = 0) {
    const tab = document.getElementById('screener-tab');
    const screener = tab?.querySelector('.screener-section');
    if (!tab || !screener) {
      if (attempt < 80) setTimeout(() => installShell(attempt + 1), 100);
      return false;
    }
    if (tab.dataset.aiLedgerInstalled === '1') return true;

    tab.dataset.aiLedgerInstalled = '1';
    const holder = document.createElement('div');
    holder.className = 'discovery-ledger-shell';
    holder.innerHTML = shellMarkup();
    tab.insertBefore(holder, screener);
    screener.dataset.discoveryPanel = 'screener';
    holder.appendChild(screener);

    holder.querySelectorAll('[data-discovery-view]').forEach((button) => {
      button.addEventListener('click', () => openView(button.dataset.discoveryView || 'screener'));
    });

    holder.querySelector('[data-ledger-search]')?.addEventListener('input', (event) => {
      state.query = event.currentTarget.value.trim().toLowerCase();
      resetAndRender();
    });
    holder.querySelector('[data-ledger-period]')?.addEventListener('change', (event) => {
      state.period = event.currentTarget.value;
      resetAndRender();
    });
    holder.querySelector('[data-ledger-performance]')?.addEventListener('change', (event) => {
      state.performance = event.currentTarget.value;
      resetAndRender();
    });
    holder.querySelector('[data-ledger-sort]')?.addEventListener('change', (event) => {
      state.sort = event.currentTarget.value;
      resetAndRender();
    });
    holder.querySelector('[data-monitor-status]')?.addEventListener('change', (event) => {
      state.monitorStatus = event.currentTarget.value;
      renderMonitor();
    });
    holder.querySelector('[data-ledger-more]')?.addEventListener('click', () => {
      state.visibleCount += PAGE_SIZE;
      renderRows();
    });

    holder.addEventListener('click', (event) => {
      const row = event.target.closest('[data-ledger-row]');
      if (!row) return;
      const id = row.dataset.ledgerRow;
      const detail = holder.querySelector(`[data-ledger-detail="${CSS.escape(id)}"]`);
      if (!detail) return;
      const willOpen = detail.hidden;
      detail.hidden = !willOpen;
      row.setAttribute('aria-expanded', String(willOpen));
    });

    const params = new URLSearchParams(window.location.search);
    if (params.get('view') === 'ai-picks') {
      setTimeout(() => openView('ai-picks'), 0);
    }
    return true;
  }

  function openMainScreener() {
    const bottom = document.querySelector('[data-app-mode="discover"], [data-app-mode="screener"]');
    if (bottom && !bottom.classList.contains('active')) bottom.click();
    const button = document.querySelector('[data-tab="screener"]');
    if (button && !button.classList.contains('active')) button.click();
  }

  function openView(view) {
    if (!installShell()) return;
    state.activeView = view === 'ai-picks' || view === 'pick-monitor' ? view : 'screener';
    const tab = document.getElementById('screener-tab');
    tab?.querySelectorAll('[data-discovery-view]').forEach((button) => {
      const active = button.dataset.discoveryView === state.activeView;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    tab?.querySelectorAll('[data-discovery-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.discoveryPanel !== state.activeView;
    });
    if (state.activeView === 'ai-picks' || state.activeView === 'pick-monitor') {
      openMainScreener();
      loadLedger();
    }
  }

  async function fetchJson(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
    return response.json();
  }

  async function loadLedger(force = false) {
    if (state.loading || (state.loaded && !force)) {
      if (state.loaded) renderAll();
      return;
    }
    state.loading = true;
    const content = document.querySelector('[data-ledger-content]');
    if (content) content.innerHTML = '<div class="ai-ledger-empty">AI PICK 기록을 불러오는 중입니다.</div>';
    try {
      const [recData, dailyData, monitorData] = await Promise.all([
        fetchJson('/static/data/ai_recommendations.json?v=ledger52'),
        fetchJson('/static/data/ai_daily_rankings.json?v=ledger52'),
        fetchJson('/static/data/pick_monitor.json?v=monitor1'),
      ]);
      state.rows = Array.isArray(recData?.recommendations) ? recData.recommendations : [];
      state.days = Array.isArray(dailyData?.days) ? dailyData.days : [];
      state.monitorPicks = Array.isArray(monitorData?.picks) ? monitorData.picks : [];
      state.monitorUpdated = monitorData?.generatedAt || monitorData?.reviewSourceUpdated || '';
      state.loaded = true;
      state.visibleCount = PAGE_SIZE;
      renderAll();
    } catch (error) {
      state.loaded = false;
      if (content) {
        content.innerHTML = '<div class="ai-ledger-empty">추천 기록을 불러오지 못했습니다.<button type="button" class="ai-ledger-retry" data-ledger-retry>다시 시도</button></div>';
        content.querySelector('[data-ledger-retry]')?.addEventListener('click', () => loadLedger(true), { once: true });
      }
      console.error('[AI PICK ledger]', error);
    } finally {
      state.loading = false;
    }
  }

  function renderKpis() {
    const host = document.querySelector('[data-ledger-kpis]');
    if (!host) return;
    const rows = state.rows;
    const dayCount = new Set(state.days.map((day) => day.tradeDate).filter(Boolean)).size || new Set(rows.map((row) => row.recommendedDate).filter(Boolean)).size;
    const evaluated = rows.filter((row) => number(row.returnPct) != null);
    const wins = evaluated.filter((row) => number(row.returnPct) > 0).length;
    const avg = evaluated.length ? evaluated.reduce((sum, row) => sum + number(row.returnPct), 0) / evaluated.length : null;
    host.innerHTML = `
      <div class="ai-ledger-kpi"><span>누적 추천일</span><b>${dayCount.toLocaleString('ko-KR')}</b></div>
      <div class="ai-ledger-kpi"><span>누적 추천 건수</span><b>${rows.length.toLocaleString('ko-KR')}</b></div>
      <div class="ai-ledger-kpi"><span>수익 구간 비율</span><b>${evaluated.length ? `${Math.round(wins / evaluated.length * 100)}%` : '-'}</b><small>평가 ${evaluated.length}/${rows.length}건</small></div>
      <div class="ai-ledger-kpi"><span>추천 건별 단순 평균 수익률</span><b class="${cls(avg)}">${pct(avg)}</b><small>전체 기록 기준 · 미평가 제외</small></div>`;

    const latest = rows.reduce((max, row) => String(row.lastUpdatedTradeDate || '') > max ? String(row.lastUpdatedTradeDate || '') : max, '');
    const date = document.querySelector('[data-ledger-date]');
    if (date) date.textContent = latest ? `${latest} 종가 기준` : '누적 기록';
  }

  function filteredRows() {
    let rows = [...state.rows];
    if (state.query) {
      rows = rows.filter((row) => `${row.name || ''} ${row.code || ''} ${row.symbol || ''}`.toLowerCase().includes(state.query));
    }
    if (state.performance === 'win') rows = rows.filter((row) => (number(row.returnPct) || 0) > 0);
    if (state.performance === 'loss') rows = rows.filter((row) => (number(row.returnPct) || 0) < 0);

    if (state.period !== 'all' && rows.length) {
      const days = Number(state.period);
      const today = Date.now();
      const cutoff = today - Math.max(0, days - 1) * 86400000;
      rows = rows.filter((row) => dateValue(row.recommendedDate) >= cutoff);
    }

    const byLatest = (a, b) => dateValue(b.recommendedDate) - dateValue(a.recommendedDate) || Number(a.rank || 99) - Number(b.rank || 99);
    if (state.sort === 'return') rows.sort((a, b) => (number(b.returnPct) ?? -Infinity) - (number(a.returnPct) ?? -Infinity) || byLatest(a, b));
    else if (state.sort === 'best') rows.sort((a, b) => (number(b.bestReturnPct) ?? -Infinity) - (number(a.bestReturnPct) ?? -Infinity) || byLatest(a, b));
    else if (state.sort === 'score') rows.sort((a, b) => (number(b.score) ?? -Infinity) - (number(a.score) ?? -Infinity) || byLatest(a, b));
    else rows.sort(byLatest);
    return rows;
  }

  function rowMarkup(row, index) {
    const id = `ledger-${String(row.recommendedDate || 'date')}-${String(row.rank || index)}-${String(row.code || row.symbol || index)}`.replace(/[^a-zA-Z0-9_-]/g, '-');
    return `
      <div class="ai-ledger-item">
        <button type="button" class="ai-ledger-row" data-ledger-row="${esc(id)}" aria-expanded="false">
          <span class="ai-ledger-cell ledger-date" data-label="추천일">${esc(row.recommendedDate || '-')}</span>
          <span class="ai-ledger-cell ledger-stock" data-label="종목"><strong>${esc(row.name || row.symbol || '-')}</strong><small>${esc(row.code || String(row.symbol || '').split('.')[0] || '')}</small></span>
          <span class="ai-ledger-cell ledger-entry" data-label="추천가">${price(row.recommendedPrice)}</span>
          <span class="ai-ledger-cell ledger-current" data-label="현재가">${price(row.currentPrice)}</span>
          <span class="ai-ledger-cell ledger-return ${cls(row.returnPct)}" data-label="수익률">${pct(row.returnPct)}</span>
          <span class="ai-ledger-cell ledger-best ${cls(row.bestReturnPct)}" data-label="최고수익률">${pct(row.bestReturnPct)}</span>
          <span class="ai-ledger-cell ledger-score" data-label="점수">${number(row.score) == null ? '-' : `${Math.round(number(row.score))}점`}</span>
          <span class="ai-ledger-chevron" aria-hidden="true">⌄</span>
        </button>
        <div class="ai-ledger-detail" data-ledger-detail="${esc(id)}" hidden>
          <div class="ai-ledger-detail-meta"><span>${esc(row.grade || '관찰')}</span><span>${esc(row.statusLabel || '성과 추적 중')}</span></div>
          <p>${esc(row.reason || '추천 사유가 기록되지 않았습니다.')}</p>
        </div>
      </div>`;
  }

  function renderRows() {
    const content = document.querySelector('[data-ledger-content]');
    const summary = document.querySelector('[data-ledger-summary]');
    const more = document.querySelector('[data-ledger-more]');
    if (!content || !summary || !more) return;
    const rows = filteredRows();
    const visible = rows.slice(0, state.visibleCount);
    summary.textContent = `${rows.length.toLocaleString('ko-KR')}개 기록 · ${visible.length.toLocaleString('ko-KR')}개 표시`;

    if (!rows.length) {
      content.innerHTML = '<div class="ai-ledger-empty">조건에 맞는 추천 기록이 없습니다.<button type="button" class="ai-ledger-reset" data-ledger-reset>필터 초기화</button></div>';
      content.querySelector('[data-ledger-reset]')?.addEventListener('click', resetFilters, { once: true });
      more.hidden = true;
      return;
    }

    content.innerHTML = `
      <div class="ai-ledger-table" role="table" aria-label="AI PICK 추천 원장">
        <div class="ai-ledger-table-head" role="row">
          <span>추천일</span><span>종목</span><span>추천가</span><span>현재가</span><span>수익률</span><span>최고수익률</span><span>점수</span><span aria-hidden="true"></span>
        </div>
        <div class="ai-ledger-table-body">${visible.map(rowMarkup).join('')}</div>
      </div>`;
    more.hidden = visible.length >= rows.length;
    more.textContent = `더 보기 · ${Math.min(PAGE_SIZE, rows.length - visible.length).toLocaleString('ko-KR')}개`;
  }

  function monitorStatusMeta(status) {
    const map = {
      SELL_REVIEW: { label: '매도검토', icon: '🔴', cls: 'sell-review', order: 0 },
      WATCH: { label: '경계', icon: '🟡', cls: 'watch', order: 1 },
      PENDING_REVIEW: { label: '검토 대기', icon: '⚪', cls: 'pending', order: 2 },
      KEEP: { label: '유지', icon: '🟢', cls: 'keep', order: 3 },
      EXIT: { label: '종료', icon: '✓', cls: 'exit', order: 4 },
    };
    return map[status] || map.PENDING_REVIEW;
  }

  function recommendationForPick(pick) {
    return state.rows.find((row) =>
      String(row.recommendedDate || '') === String(pick.pickDate || '') &&
      String(row.code || String(row.symbol || '').split('.')[0] || '') === String(pick.code || '')
    ) || null;
  }

  function monitorRows() {
    let rows = [...state.monitorPicks];
    if (state.monitorStatus !== 'all') rows = rows.filter((row) => row.status === state.monitorStatus);
    rows.sort((a, b) => {
      const statusDiff = monitorStatusMeta(a.status).order - monitorStatusMeta(b.status).order;
      if (statusDiff) return statusDiff;
      return dateValue(b.pickDate) - dateValue(a.pickDate) || Number(a.rank || 99) - Number(b.rank || 99);
    });
    return rows;
  }

  function evidenceMarkup(pick) {
    const evidence = Array.isArray(pick?.monitor?.evidence) ? pick.monitor.evidence : [];
    if (!evidence.length) return '<p class="ai-monitor-muted">추천 이후 검증 가능한 신규 근거를 아직 확보하지 못했습니다.</p>';
    return `<div class="ai-monitor-evidence">${evidence.slice(0, 4).map((item) => {
      const title = item.sourceTitle || item.sourceUrl || '근거';
      const fact = item.fact || '';
      const date = item.publishedAt || '';
      return `<a href="${esc(item.sourceUrl)}" target="_blank" rel="noopener noreferrer"><span>${esc(date)}</span><strong>${esc(title)}</strong><small>${esc(fact)}</small></a>`;
    }).join('')}</div>`;
  }

  function monitorCardMarkup(pick) {
    const meta = monitorStatusMeta(pick.status);
    const rec = recommendationForPick(pick);
    const thesis = pick?.originalThesis?.summary || (Array.isArray(pick?.originalThesis?.pillars) ? pick.originalThesis.pillars.join(' · ') : '') || '추천 당시 투자논리 기록 없음';
    const reviewReason = pick?.monitor?.reason || '최신 검토 대기';
    const reviewed = pick?.monitor?.lastReviewedTradeDate || String(pick?.monitor?.lastReviewedAt || '').slice(0, 10);
    return `
      <article class="ai-monitor-card ai-monitor-${meta.cls}">
        <div class="ai-monitor-card-head">
          <div><strong>${esc(pick.name || pick.symbol || '-')}</strong><small>${esc(pick.code || '')} · ${esc(pick.pickDate || '-')} PICK</small></div>
          <span class="ai-monitor-status ai-monitor-status-${meta.cls}">${meta.icon} ${meta.label}</span>
        </div>
        <div class="ai-monitor-metrics">
          <span>추천가 <b>${price(pick.pickPrice)}</b></span>
          <span>최근가 <b>${price(rec?.currentPrice)}</b></span>
          <span>수익률 <b class="${cls(rec?.returnPct)}">${pct(rec?.returnPct)}</b></span>
          <span>시세기준 <b>${esc(rec?.lastUpdatedTradeDate || '-')}</b></span>
        </div>
        <div class="ai-monitor-block"><b>추천 당시 논리</b><p>${esc(thesis)}</p></div>
        <div class="ai-monitor-block"><b>최근 점검</b><p>${esc(reviewReason)}</p></div>
        <div class="ai-monitor-block"><b>검증 근거</b>${evidenceMarkup(pick)}</div>
        <div class="ai-monitor-foot"><span>마지막 검토 ${esc(reviewed || '대기')}</span>${pick.needsUserReview ? '<strong>사용자 확인 필요</strong>' : ''}</div>
      </article>`;
  }

  function renderMonitor() {
    const host = document.querySelector('[data-monitor-content]');
    const kpis = document.querySelector('[data-monitor-kpis]');
    const date = document.querySelector('[data-monitor-date]');
    if (!host || !kpis) return;

    const counts = { KEEP: 0, WATCH: 0, SELL_REVIEW: 0, PENDING_REVIEW: 0, EXIT: 0 };
    state.monitorPicks.forEach((row) => { counts[row.status] = (counts[row.status] || 0) + 1; });
    kpis.innerHTML = `
      <div class="ai-monitor-kpi keep"><span>🟢 유지</span><b>${counts.KEEP || 0}</b></div>
      <div class="ai-monitor-kpi watch"><span>🟡 경계</span><b>${counts.WATCH || 0}</b></div>
      <div class="ai-monitor-kpi sell-review"><span>🔴 매도검토</span><b>${counts.SELL_REVIEW || 0}</b></div>
      <div class="ai-monitor-kpi pending"><span>⚪ 검토 대기</span><b>${counts.PENDING_REVIEW || 0}</b></div>`;
    if (date) date.textContent = state.monitorUpdated ? `${String(state.monitorUpdated).slice(0, 10)} 점검 기준` : '점검일 미확인';

    const rows = monitorRows();
    if (!rows.length) {
      host.innerHTML = '<div class="ai-ledger-empty">해당 상태의 PICK이 없습니다.</div>';
      return;
    }
    host.innerHTML = rows.map(monitorCardMarkup).join('');
  }

  function renderAll() {
    renderKpis();
    renderRows();
    renderMonitor();
  }

  function resetAndRender() {
    state.visibleCount = PAGE_SIZE;
    renderRows();
  }

  function resetFilters() {
    state.query = '';
    state.period = 'all';
    state.performance = 'all';
    state.sort = 'latest';
    state.visibleCount = PAGE_SIZE;
    const search = document.querySelector('[data-ledger-search]');
    const period = document.querySelector('[data-ledger-period]');
    const performance = document.querySelector('[data-ledger-performance]');
    const sort = document.querySelector('[data-ledger-sort]');
    if (search) search.value = '';
    if (period) period.value = 'all';
    if (performance) performance.value = 'all';
    if (sort) sort.value = 'latest';
    renderRows();
  }

  window.__openScreenerDiscoveryView = () => openView('screener');

  window.__openAiPickLedger = () => {
    openMainScreener();
    if (!installShell()) {
      setTimeout(() => window.__openAiPickLedger?.(), 120);
      return;
    }
    openView('ai-picks');
  };

  function boot() {
    installShell();
    const params = new URLSearchParams(window.location.search);
    if (params.get('tab') === 'screener' && params.get('view') === 'ai-picks') {
      setTimeout(() => window.__openAiPickLedger(), 80);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
