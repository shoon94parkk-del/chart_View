(() => {
  'use strict';

  const PAGE_SIZE = 60;
  const state = {
    rows: [],
    days: [],
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
        <button type="button" class="discovery-subtab" data-discovery-view="ai-picks" role="tab" aria-selected="false">AI PICK 기록</button>
      </div>
      <section class="ai-ledger-panel" data-discovery-panel="ai-picks" hidden aria-label="AI PICK 누적 기록">
        <div class="ai-ledger-head">
          <div>
            <span class="ai-ledger-eyebrow">CHARTVIEW AI PICK</span>
            <h2>누적 추천 원장</h2>
            <p>하루 3개씩 쌓이는 추천 종목을 한 화면에서 비교하고, 필요한 행만 펼쳐 추천 사유를 확인합니다.</p>
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
    const button = document.querySelector('[data-tab="screener"]');
    if (button && !button.classList.contains('active')) button.click();
    const bottom = document.querySelector('[data-app-mode="screener"], [data-app-mode="discover"]');
    if (bottom && !document.getElementById('screener-tab')?.classList.contains('active')) bottom.click();
  }

  function openView(view) {
    if (!installShell()) return;
    state.activeView = view === 'ai-picks' ? 'ai-picks' : 'screener';
    const tab = document.getElementById('screener-tab');
    tab?.querySelectorAll('[data-discovery-view]').forEach((button) => {
      const active = button.dataset.discoveryView === state.activeView;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    tab?.querySelectorAll('[data-discovery-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.discoveryPanel !== state.activeView;
    });
    if (state.activeView === 'ai-picks') {
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
      const [recData, dailyData] = await Promise.all([
        fetchJson('/static/data/ai_recommendations.json?v=ledger52'),
        fetchJson('/static/data/ai_daily_rankings.json?v=ledger52'),
      ]);
      state.rows = Array.isArray(recData?.recommendations) ? recData.recommendations : [];
      state.days = Array.isArray(dailyData?.days) ? dailyData.days : [];
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
    const wins = rows.filter((row) => (number(row.returnPct) || 0) > 0).length;
    const avg = rows.length ? rows.reduce((sum, row) => sum + (number(row.returnPct) || 0), 0) / rows.length : 0;
    host.innerHTML = `
      <div class="ai-ledger-kpi"><span>누적 추천일</span><b>${dayCount.toLocaleString('ko-KR')}</b></div>
      <div class="ai-ledger-kpi"><span>누적 추천 건수</span><b>${rows.length.toLocaleString('ko-KR')}</b></div>
      <div class="ai-ledger-kpi"><span>수익 구간 비율</span><b>${rows.length ? Math.round(wins / rows.length * 100) : 0}%</b></div>
      <div class="ai-ledger-kpi"><span>평균 수익률</span><b class="${cls(avg)}">${pct(avg)}</b></div>`;

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
      const latest = Math.max(...state.rows.map((row) => dateValue(row.recommendedDate)));
      const cutoff = latest - Math.max(0, days - 1) * 86400000;
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
          <span class="ai-ledger-cell ledger-rank" data-label="순위">${esc(row.rank || '-')}위</span>
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
          <span>추천일</span><span>순위</span><span>종목</span><span>추천가</span><span>현재가</span><span>수익률</span><span>최고수익률</span><span>점수</span><span aria-hidden="true"></span>
        </div>
        <div class="ai-ledger-table-body">${visible.map(rowMarkup).join('')}</div>
      </div>`;
    more.hidden = visible.length >= rows.length;
    more.textContent = `더 보기 · ${Math.min(PAGE_SIZE, rows.length - visible.length).toLocaleString('ko-KR')}개`;
  }

  function renderAll() {
    renderKpis();
    renderRows();
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
