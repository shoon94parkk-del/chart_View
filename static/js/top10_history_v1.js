(() => {
  'use strict';

  const state = {
    days: [],
    loaded: false,
    loading: false,
    query: '',
    coverage: 'all',
    sort: 'latest',
  };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  function dateValue(value) {
    const t = Date.parse(`${String(value || '')}T00:00:00+09:00`);
    return Number.isFinite(t) ? t : 0;
  }

  function selectedSet(day) {
    return new Set((day.selectedPicks || []).map((x) => String(x.code || x.name || '')));
  }

  function isSelected(day, row) {
    const set = selectedSet(day);
    return set.has(String(row.code || '')) || set.has(String(row.name || ''));
  }

  function shell() {
    return `
      <section class="top10-history-panel" data-discovery-panel="top10-history" hidden aria-label="TOP10 추천 히스토리">
        <div class="top10-history-head">
          <div>
            <span class="top10-history-eyebrow">DAILY TOP10 ARCHIVE</span>
            <h2>TOP10 히스토리</h2>
            <p>매일 실제로 제시한 TOP10과 그날 사용자가 최종 선택한 PICK을 함께 보관합니다. 초기 기록이 불완전한 날은 임의 보정하지 않고 부분 기록으로 표시합니다.</p>
          </div>
          <span class="top10-history-date" data-top10-updated>불러오는 중</span>
        </div>
        <div class="top10-history-kpis" data-top10-kpis></div>
        <div class="top10-history-tools">
          <label class="top10-history-search-wrap">
            <span class="sr-only">TOP10 종목 검색</span>
            <input type="search" class="top10-history-search" data-top10-search placeholder="종목명 · 코드 검색" autocomplete="off">
          </label>
          <select class="top10-history-select" data-top10-coverage aria-label="기록 완전성 필터">
            <option value="all">전체 기록</option>
            <option value="complete">TOP10 전체</option>
            <option value="partial">부분 기록</option>
          </select>
          <select class="top10-history-select" data-top10-sort aria-label="날짜 정렬">
            <option value="latest">최신순</option>
            <option value="oldest">과거순</option>
          </select>
        </div>
        <div class="top10-history-legend">
          <span><b class="legend-dot selected"></b> 사용자 최종 PICK</span>
          <span><b class="legend-dot partial"></b> 일부 기록만 존재</span>
          <span>점수는 당시 대화에 표시된 원점수 그대로이며 날짜 간 절대 비교용으로 정규화하지 않습니다.</span>
        </div>
        <div class="top10-history-summary" data-top10-summary></div>
        <div class="top10-history-content" data-top10-content>
          <div class="top10-history-empty">TOP10 기록을 불러오는 중입니다.</div>
        </div>
      </section>`;
  }

  function ensureUi(attempt = 0) {
    const tab = document.getElementById('screener-tab');
    const nav = tab?.querySelector('.discovery-subnav');
    const shellHost = tab?.querySelector('.discovery-ledger-shell');
    if (!tab || !nav || !shellHost) {
      if (attempt < 120) setTimeout(() => ensureUi(attempt + 1), 100);
      return;
    }
    if (tab.dataset.top10HistoryInstalled === '1') return;
    tab.dataset.top10HistoryInstalled = '1';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'discovery-subtab';
    button.dataset.discoveryView = 'top10-history';
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', 'false');
    button.textContent = 'TOP10 히스토리';
    nav.appendChild(button);

    const holder = document.createElement('div');
    holder.innerHTML = shell();
    const panel = holder.firstElementChild;
    shellHost.appendChild(panel);

    button.addEventListener('click', () => openHistory());
    panel.querySelector('[data-top10-search]')?.addEventListener('input', (event) => {
      state.query = event.currentTarget.value.trim().toLowerCase();
      render();
    });
    panel.querySelector('[data-top10-coverage]')?.addEventListener('change', (event) => {
      state.coverage = event.currentTarget.value;
      render();
    });
    panel.querySelector('[data-top10-sort]')?.addEventListener('change', (event) => {
      state.sort = event.currentTarget.value;
      render();
    });

    const params = new URLSearchParams(window.location.search);
    if (params.get('view') === 'top10-history') setTimeout(openHistory, 0);
  }

  function openHistory() {
    const tab = document.getElementById('screener-tab');
    if (!tab) return;
    const mainTab = document.querySelector('[data-tab="screener"]');
    if (mainTab && !mainTab.classList.contains('active')) mainTab.click();

    tab.querySelectorAll('[data-discovery-view]').forEach((button) => {
      const active = button.dataset.discoveryView === 'top10-history';
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    tab.querySelectorAll('[data-discovery-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.discoveryPanel !== 'top10-history';
    });

    load();
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', 'screener');
      url.searchParams.set('view', 'top10-history');
      history.replaceState(history.state, '', url);
    } catch (_) {}
  }

  async function load(force = false) {
    if (state.loading || (state.loaded && !force)) {
      if (state.loaded) render();
      return;
    }
    state.loading = true;
    try {
      const response = await fetch('/static/data/top10_history.json?v=20261013v1', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      state.days = Array.isArray(data?.days) ? data.days : [];
      state.updated = data?.updated || '';
      state.loaded = true;
      render();
    } catch (error) {
      const host = document.querySelector('[data-top10-content]');
      if (host) {
        host.innerHTML = '<div class="top10-history-empty">TOP10 기록을 불러오지 못했습니다. <button type="button" data-top10-retry>다시 시도</button></div>';
        host.querySelector('[data-top10-retry]')?.addEventListener('click', () => load(true), { once: true });
      }
      console.error('[TOP10 history]', error);
    } finally {
      state.loading = false;
    }
  }

  function filteredDays() {
    let rows = [...state.days];
    if (state.coverage !== 'all') rows = rows.filter((d) => d.coverage === state.coverage);
    if (state.query) {
      rows = rows.filter((d) => {
        const hay = [
          d.tradeDate,
          ...(d.top10 || []).flatMap((x) => [x.name, x.code]),
          ...(d.selectedPicks || []).flatMap((x) => [x.name, x.code]),
        ].filter(Boolean).join(' ').toLowerCase();
        return hay.includes(state.query);
      });
    }
    rows.sort((a, b) => state.sort === 'oldest'
      ? dateValue(a.tradeDate) - dateValue(b.tradeDate)
      : dateValue(b.tradeDate) - dateValue(a.tradeDate));
    return rows;
  }

  function renderKpis() {
    const host = document.querySelector('[data-top10-kpis]');
    if (!host) return;
    const days = state.days;
    const full = days.filter((d) => d.coverage === 'complete').length;
    const recommendationRows = days.reduce((sum, d) => sum + (d.top10 || []).length, 0);
    const confirmed = days.reduce((sum, d) => sum + (d.selectedPicks || []).filter((x) => x.status === 'user_confirmed').length, 0);
    const unique = new Set(days.flatMap((d) => (d.top10 || []).map((x) => x.code || x.name).filter(Boolean))).size;
    host.innerHTML = `
      <div class="top10-history-kpi"><span>기록일</span><b>${days.length}</b></div>
      <div class="top10-history-kpi"><span>완전 TOP10</span><b>${full}</b></div>
      <div class="top10-history-kpi"><span>누적 추천 행</span><b>${recommendationRows}</b><small>고유 종목 ${unique}개</small></div>
      <div class="top10-history-kpi selected"><span>사용자 확정 PICK</span><b>${confirmed}</b></div>`;

    const updated = document.querySelector('[data-top10-updated]');
    if (updated) updated.textContent = state.updated ? `갱신 ${String(state.updated).slice(0, 10)}` : '누적 기록';
  }

  function selectedPills(day) {
    const picks = day.selectedPicks || [];
    if (!picks.length) return '<span class="top10-history-pick-empty">최종 PICK 미확정</span>';
    return picks.map((p) => {
      const legacy = p.status === 'legacy_saved';
      return `<span class="top10-history-pick ${legacy ? 'legacy' : ''}">${legacy ? '저장' : '선택'} · ${esc(p.name || p.code || '-')}</span>`;
    }).join('');
  }

  function rowMarkup(day, row) {
    const selected = isSelected(day, row);
    return `
      <div class="top10-history-row ${selected ? 'is-selected' : ''}">
        <span class="top10-history-rank">${row.rank || '-'}</span>
        <span class="top10-history-stock"><strong>${esc(row.name || '-')}</strong><small>${esc(row.code || '코드 미확인')}</small></span>
        <span class="top10-history-score">${row.score == null ? '-' : `${esc(row.score)}점`}</span>
        <span class="top10-history-selected">${selected ? 'PICK' : ''}</span>
      </div>`;
  }

  function dayMarkup(day) {
    const partial = day.coverage !== 'complete';
    const rows = day.top10 || [];
    return `
      <article class="top10-history-day ${partial ? 'is-partial' : ''}">
        <header class="top10-history-day-head">
          <div>
            <div class="top10-history-day-title">
              <strong>${esc(day.tradeDate || '-')}</strong>
              <span class="top10-history-coverage ${partial ? 'partial' : 'complete'}">${partial ? '부분 기록' : 'TOP10 전체'}</span>
            </div>
            <div class="top10-history-picks">${selectedPills(day)}</div>
          </div>
          <span class="top10-history-count">${rows.length}개 기록</span>
        </header>
        <div class="top10-history-table">
          <div class="top10-history-table-head"><span>순위</span><span>종목</span><span>당시 점수</span><span>선택</span></div>
          <div class="top10-history-table-body">${rows.map((row) => rowMarkup(day, row)).join('')}</div>
        </div>
        ${day.note ? `<p class="top10-history-note">${esc(day.note)}</p>` : ''}
      </article>`;
  }

  function render() {
    renderKpis();
    const host = document.querySelector('[data-top10-content]');
    const summary = document.querySelector('[data-top10-summary]');
    if (!host || !summary) return;
    const rows = filteredDays();
    summary.textContent = `${rows.length}개 날짜 표시 · 실제 대화 기록 기준`;
    if (!rows.length) {
      host.innerHTML = '<div class="top10-history-empty">조건에 맞는 TOP10 기록이 없습니다.</div>';
      return;
    }
    host.innerHTML = rows.map(dayMarkup).join('');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => ensureUi(), { once: true });
  else ensureUi();
})();