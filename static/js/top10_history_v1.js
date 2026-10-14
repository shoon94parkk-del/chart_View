(() => {
  'use strict';

  const state = {
    days: [],
    loaded: false,
    loading: false,
    query: '',
    coverage: 'all',
    sort: 'latest',
    performance: new Map(),
    observers: [],
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

  function todayKst() {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(new Date());
    const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
    return `${map.year}-${map.month}-${map.day}`;
  }

  function selectedSet(day) {
    return new Set((day.selectedPicks || []).flatMap((x) => [String(x.code || ''), String(x.name || ''), String(x.symbol || '')]));
  }

  function isSelected(day, row) {
    const set = selectedSet(day);
    return set.has(String(row.code || '')) || set.has(String(row.name || '')) || set.has(String(row.symbol || ''));
  }

  function shell() {
    return `
      <section class="top10-history-panel" data-discovery-panel="top10-history" hidden aria-label="TOP10 추천 히스토리">
        <div class="top10-history-head">
          <div>
            <span class="top10-history-eyebrow">DAILY TOP10 ARCHIVE</span>
            <h2>TOP10 히스토리</h2>
            <p>매일 실제로 제시한 TOP10과 사용자 최종 PICK, 추천일 종가 대비 실제 성과를 함께 보관합니다.</p>
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
          <span><b class="legend-dot return"></b> 수익률 기준: 추천일 정규장 종가</span>
          <span>5D·20D·60D는 추천 후 해당 거래일 종가이며 아직 지나지 않았으면 — 표시</span>
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
      const response = await fetch('/static/data/top10_history.json?v=20261013v3', { cache: 'no-store' });
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
          ...(d.top10 || []).flatMap((x) => [x.name, x.code, x.symbol]),
          ...(d.selectedPicks || []).flatMap((x) => [x.name, x.code, x.symbol]),
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

  function formatPrice(value) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return Math.round(n).toLocaleString('ko-KR');
  }

  function formatReturn(value) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    const sign = n > 0 ? '+' : '';
    return `${sign}${n.toFixed(1)}%`;
  }

  function returnClass(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return 'flat';
    return n > 0 ? 'up' : 'down';
  }

  function perfCell(field, label, value = null) {
    return `<span class="top10-history-perf ${returnClass(value)}" data-perf-field="${field}"><small>${label}</small><b>${field === 'base' || field === 'latest' ? formatPrice(value) : formatReturn(value)}</b></span>`;
  }

  function rowMarkup(day, row) {
    const selected = isSelected(day, row);
    const symbol = row.symbol || '';
    const perf = state.performance.get(day.tradeDate)?.rows?.get(symbol) || null;
    return `
      <div class="top10-history-row ${selected ? 'is-selected' : ''}" data-perf-key="${esc(day.tradeDate)}:${esc(symbol)}">
        <span class="top10-history-rank">${row.rank || '-'}</span>
        <span class="top10-history-stock"><strong>${esc(row.name || '-')}</strong><small>${esc(row.code || '코드 미확인')}</small></span>
        <span class="top10-history-score">${row.score == null ? '-' : `${esc(row.score)}점`}</span>
        <div class="top10-history-performance">
          ${perfCell('base','추천가',perf?.base ?? row.recommendedPrice ?? row.recommendationClose ?? null)}
          ${perfCell('latest','현재가',perf?.latest)}
          ${perfCell('current','현재',perf?.current)}
          ${perfCell('d5','5D',perf?.d5)}
          ${perfCell('d20','20D',perf?.d20)}
          ${perfCell('d60','60D',perf?.d60)}
        </div>
        <span class="top10-history-selected">${selected ? 'PICK' : ''}</span>
      </div>`;
  }

  function dayAverage(day) {
    const block = state.performance.get(day.tradeDate);
    if (!block?.rows) return null;
    // User-selected securities outside the original TOP10 must not change TOP10 averages.
    const values = (day.top10 || [])
      .map((row) => block.rows.get(row.symbol)?.current)
      .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
      .map(Number);
    if (!values.length) return null;
    return values.reduce((a, b) => a + b, 0) / values.length;
  }

  function dayMarkup(day) {
    const partial = day.coverage !== 'complete';
    const rows = day.top10 || [];
    const outsidePicks = (day.selectedPicks || [])
      .filter((pick) => pick.selectedOutsideTop10 && !rows.some((row) => row.code === pick.code))
      .map((pick) => ({
        rank: '별도', name: pick.name, code: pick.code, symbol: pick.symbol,
        score: null, recommendationClose: pick.recommendationClose
      }));
    const avg = dayAverage(day);
    const perfStatus = state.performance.get(day.tradeDate)?.status;
    return `
      <article class="top10-history-day ${partial ? 'is-partial' : ''}" data-top10-date="${esc(day.tradeDate)}">
        <header class="top10-history-day-head">
          <div>
            <div class="top10-history-day-title">
              <strong>${esc(day.tradeDate || '-')}</strong>
              <span class="top10-history-coverage ${partial ? 'partial' : 'complete'}">${partial ? '부분 기록' : 'TOP10 전체'}</span>
            </div>
            <div class="top10-history-picks">${selectedPills(day)}</div>
          </div>
          <div class="top10-history-day-stats">
            <span class="top10-history-count">${rows.length}개 기록</span>
            <span class="top10-history-average ${returnClass(avg)}" data-day-average>
              ${Number.isFinite(avg) ? `TOP10 평균 현재 ${formatReturn(avg)}` : (perfStatus === 'error' ? '수익률 조회 실패' : '수익률 계산 중')}
            </span>
          </div>
        </header>
        <div class="top10-history-table">
          <div class="top10-history-table-head"><span>순위</span><span>종목</span><span>점수</span><span>추천일 대비 성과</span><span>선택</span></div>
          <div class="top10-history-table-body">${rows.map((row) => rowMarkup(day, row)).join('')}</div>
        </div>
        ${outsidePicks.length ? `
          <p class="top10-history-note"><strong>TOP10 외 사용자 선정 PICK</strong> · 추천일 종가 대비 별도 추적</p>
          <div class="top10-history-table">
            <div class="top10-history-table-body">${outsidePicks.map((row) => rowMarkup(day, row)).join('')}</div>
          </div>
        ` : ''}
        ${day.note ? `<p class="top10-history-note">${esc(day.note)}</p>` : ''}
      </article>`;
  }

  function chunk(items, size) {
    const out = [];
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
    return out;
  }

  function metricAt(data, index, base) {
    if (!Array.isArray(data) || data.length <= index || !Number.isFinite(base) || base <= 0) return null;
    const px = Number(data[index]?.price);
    if (!Number.isFinite(px)) return null;
    return ((px - base) / base) * 100;
  }

  async function loadDayPerformance(day) {
    const existing = state.performance.get(day.tradeDate);
    if (existing?.status === 'loading' || existing?.status === 'done') return;
    const outsidePicks = (day.selectedPicks || []).filter((pick) => pick.selectedOutsideTop10);
    const symbols = [...new Set([...(day.top10 || []), ...outsidePicks].map((x) => x.symbol).filter(Boolean))];
    if (!symbols.length) {
      state.performance.set(day.tradeDate, { status: 'error', rows: new Map() });
      applyPerformance(day.tradeDate);
      return;
    }

    const block = { status: 'loading', rows: new Map() };
    state.performance.set(day.tradeDate, block);
    const end = todayKst();

    try {
      for (const group of chunk(symbols, 6)) {
        const params = new URLSearchParams({
          tickers: group.join(','),
          start: day.tradeDate,
          end,
        });
        const response = await fetch(`/api/compare?${params.toString()}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`performance HTTP ${response.status}`);
        const payload = await response.json();
        for (const stock of (payload.stocks || [])) {
          const points = Array.isArray(stock.data) ? stock.data : [];
          const base = Number(points[0]?.price);
          const latest = Number(points.at(-1)?.price);
          if (!Number.isFinite(base) || !Number.isFinite(latest) || base <= 0) continue;
          block.rows.set(stock.ticker, {
            base,
            latest,
            current: ((latest - base) / base) * 100,
            d5: metricAt(points, 5, base),
            d20: metricAt(points, 20, base),
            d60: metricAt(points, 60, base),
            observations: points.length,
            startDate: stock.startDate || day.tradeDate,
            endDate: stock.endDate || end,
          });
        }
      }
      block.status = 'done';
    } catch (error) {
      block.status = 'error';
      console.error('[TOP10 history performance]', day.tradeDate, error);
    }
    applyPerformance(day.tradeDate);
  }

  function applyPerformance(tradeDate) {
    const article = document.querySelector(`[data-top10-date="${CSS.escape(tradeDate)}"]`);
    const block = state.performance.get(tradeDate);
    if (!article || !block) return;

    article.querySelectorAll('[data-perf-key]').forEach((rowEl) => {
      const symbol = rowEl.getAttribute('data-perf-key').split(':').slice(1).join(':');
      const perf = block.rows?.get(symbol);
      if (!perf) return;
      const values = { base: perf.base, latest: perf.latest, current: perf.current, d5: perf.d5, d20: perf.d20, d60: perf.d60 };
      Object.entries(values).forEach(([field, value]) => {
        const cell = rowEl.querySelector(`[data-perf-field="${field}"]`);
        if (!cell) return;
        const b = cell.querySelector('b');
        if (b) b.textContent = field === 'base' || field === 'latest' ? formatPrice(value) : formatReturn(value);
        cell.classList.remove('up','down','flat');
        cell.classList.add(returnClass(value));
      });
    });

    const avg = dayAverage(state.days.find((day) => day.tradeDate === tradeDate) || { tradeDate, top10: [] });
    const avgEl = article.querySelector('[data-day-average]');
    if (avgEl) {
      avgEl.classList.remove('up','down','flat');
      if (Number.isFinite(avg)) {
        avgEl.textContent = `TOP10 평균 현재 ${formatReturn(avg)}`;
        avgEl.classList.add(returnClass(avg));
      } else {
        avgEl.textContent = block.status === 'error' ? '수익률 조회 실패' : '수익률 없음';
        avgEl.classList.add('flat');
      }
    }
  }

  function observeDays() {
    state.observers.forEach((o) => o.disconnect?.());
    state.observers = [];
    const cards = [...document.querySelectorAll('[data-top10-date]')];
    if (!('IntersectionObserver' in window)) {
      cards.forEach((card) => {
        const day = state.days.find((d) => d.tradeDate === card.dataset.top10Date);
        if (day) loadDayPerformance(day);
      });
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const date = entry.target.dataset.top10Date;
        const day = state.days.find((d) => d.tradeDate === date);
        if (day) loadDayPerformance(day);
        observer.unobserve(entry.target);
      }
    }, { rootMargin: '500px 0px' });
    cards.forEach((card) => observer.observe(card));
    state.observers.push(observer);
  }

  function render() {
    renderKpis();
    const host = document.querySelector('[data-top10-content]');
    const summary = document.querySelector('[data-top10-summary]');
    if (!host || !summary) return;
    const rows = filteredDays();
    summary.textContent = `${rows.length}개 날짜 표시 · 추천일 종가 대비 현재/5D/20D/60D 자동 계산`;
    if (!rows.length) {
      host.innerHTML = '<div class="top10-history-empty">조건에 맞는 TOP10 기록이 없습니다.</div>';
      return;
    }
    host.innerHTML = rows.map(dayMarkup).join('');
    requestAnimationFrame(observeDays);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => ensureUi(), { once: true });
  else ensureUi();
})();