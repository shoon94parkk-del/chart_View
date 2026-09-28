(() => {
  'use strict';

  const VERSION = '20260928-pick-management-v2';
  const PAGE_SIZE = 60;
  const STATUS = {
    SELL_REVIEW: { label: '매도검토', icon: '🔴', cls: 'sell', order: 0 },
    WATCH: { label: '경계', icon: '🟡', cls: 'watch', order: 1 },
    PENDING_REVIEW: { label: '검토 대기', icon: '⚪', cls: 'pending', order: 2 },
    KEEP: { label: '유지', icon: '🟢', cls: 'keep', order: 3 },
    EXIT: { label: '종료', icon: '✓', cls: 'exit', order: 4 },
  };

  let installed = false;
  let open = false;
  let monitorData = null;
  let recommendationData = null;
  let visibleCount = PAGE_SIZE;
  const filters = { query: '', period: 'all', performance: 'all', status: 'all', sort: 'latest' };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const num = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  const price = (value) => {
    const n = num(value);
    return n == null ? '-' : `${Math.round(n).toLocaleString('ko-KR')}원`;
  };

  const pct = (value) => {
    const n = num(value);
    return n == null ? '-' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  };

  const returnClass = (value) => {
    const n = num(value);
    return n == null ? '' : n > 0 ? 'up' : n < 0 ? 'down' : 'flat';
  };

  const dateValue = (value) => {
    const t = Date.parse(`${String(value || '')}T00:00:00+09:00`);
    return Number.isFinite(t) ? t : 0;
  };

  function addStyle() {
    if (document.getElementById('pick-management-v2-style')) return;
    const style = document.createElement('style');
    style.id = 'pick-management-v2-style';
    style.textContent = `
      #screener-tab.pick-management-active > :not(#pick-management-direct){display:none!important}
      #pick-management-direct{padding:2px 0 30px}
      #pick-management-direct[hidden]{display:none!important}
      .pmg-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin:0 0 13px}
      .pmg-eyebrow{display:block;margin-bottom:4px;color:#3182f6;font-size:11px;font-weight:900;letter-spacing:.07em}
      .pmg-head h2{margin:0;color:#191f28;font-size:22px;letter-spacing:-.03em}
      .pmg-head p{max-width:680px;margin:6px 0 0;color:#6b7684;font-size:12px;line-height:1.55}
      .pmg-date{flex:0 0 auto;padding:5px 8px;border:1px solid #e5e8eb;border-radius:999px;color:#8b95a1;font-size:9.5px;font-weight:750;white-space:nowrap}
      .pmg-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:0 0 9px}
      .pmg-kpi{min-width:0;padding:11px 12px;border:1px solid #e5e8eb;border-radius:13px;background:#fff}
      .pmg-kpi span{display:block;color:#8b95a1;font-size:10px;font-weight:750}
      .pmg-kpi b{display:block;margin-top:4px;color:#191f28;font-size:19px;font-weight:900;font-variant-numeric:tabular-nums}
      .pmg-kpi small{display:block;margin-top:2px;color:#9aa4b0;font-size:8.5px}
      .pmg-kpi b.up{color:#e23d4a}.pmg-kpi b.down{color:#2675d9}
      .pmg-status-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:0 0 10px}
      .pmg-status-summary{padding:8px 9px;border:1px solid #e8edf3;border-radius:11px;background:#f8f9fb}
      .pmg-status-summary span{display:block;color:#6b7684;font-size:9.5px;font-weight:800}
      .pmg-status-summary b{display:block;margin-top:2px;color:#333d4b;font-size:15px;font-weight:900}
      .pmg-status-summary.keep{background:#f3fbf6;border-color:#d8f0df}.pmg-status-summary.watch{background:#fffbef;border-color:#f5e9bc}.pmg-status-summary.sell{background:#fff5f5;border-color:#f5d9dc}
      .pmg-policy{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:-1px 2px 10px;color:#8b95a1;font-size:9px;font-weight:700}
      .pmg-tools{display:grid;grid-template-columns:minmax(180px,1fr) repeat(4,minmax(105px,auto));gap:6px;margin-bottom:7px}
      .pmg-input,.pmg-select{width:100%;min-height:40px;border:1px solid #dfe3e8;border-radius:10px;background:#fff;color:#333d4b;font:inherit;font-size:11px;font-weight:700;outline:none}
      .pmg-input{padding:0 11px}.pmg-select{padding:0 26px 0 9px;cursor:pointer}
      .pmg-input:focus,.pmg-select:focus{border-color:#8ab8ff;box-shadow:0 0 0 3px rgba(49,130,246,.1)}
      .pmg-summary{min-height:21px;margin:3px 1px 7px;color:#8b95a1;font-size:10px;font-weight:750}
      .pmg-list{overflow:hidden;border:1px solid #e5e8eb;border-radius:14px;background:#fff}
      .pmg-item+.pmg-item{border-top:1px solid #edf0f3}
      .pmg-row{display:grid;grid-template-columns:86px minmax(150px,1.35fr) 86px 86px 84px 92px 58px 92px 18px;align-items:center;gap:6px;width:100%;min-height:58px;padding:8px 11px;border:0;background:#fff;color:#333d4b;text-align:left;font:inherit;cursor:pointer}
      .pmg-row:hover{background:#fafbfc}.pmg-row:focus-visible{outline:2px solid rgba(49,130,246,.3);outline-offset:-2px}
      .pmg-cell{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-variant-numeric:tabular-nums}
      .pmg-date-cell{color:#8b95a1;font-size:9.5px;font-weight:750}
      .pmg-stock{display:grid;gap:2px}.pmg-stock strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#191f28;font-size:13px;font-weight:900}.pmg-stock small{color:#9aa4b0;font-size:9px;font-weight:700}
      .pmg-return,.pmg-best,.pmg-score{font-weight:900}.pmg-return.up,.pmg-best.up{color:#e23d4a}.pmg-return.down,.pmg-best.down{color:#2675d9}
      .pmg-status{display:inline-flex;align-items:center;justify-content:center;padding:5px 7px;border-radius:999px;background:#f2f4f6;color:#6b7684;font-size:9px;font-weight:900;white-space:nowrap}
      .pmg-status.keep{background:#e8f7ed;color:#24713d}.pmg-status.watch{background:#fff4cc;color:#8a6412}.pmg-status.sell{background:#ffecef;color:#c33243}.pmg-status.exit{background:#edf0f3;color:#4e5968}
      .pmg-chevron{color:#a8b0ba;font-size:12px;transition:transform .15s ease}.pmg-row[aria-expanded="true"] .pmg-chevron{transform:rotate(180deg)}
      .pmg-detail{padding:11px 13px 13px;border-top:1px dashed #edf0f3;background:#fbfcfe}
      .pmg-detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
      .pmg-block{min-width:0;padding:9px 10px;border:1px solid #edf0f3;border-radius:10px;background:#fff}
      .pmg-block>strong{display:block;margin-bottom:4px;color:#4e5968;font-size:9.5px;font-weight:900}.pmg-block p{margin:0;color:#59636f;font-size:10.5px;line-height:1.5}
      .pmg-evidence{display:grid;gap:5px;margin-top:5px}.pmg-evidence a{display:grid;gap:2px;padding:7px 8px;border:1px solid #edf0f3;border-radius:9px;background:#fbfcfe;text-decoration:none}.pmg-evidence span{color:#9aa4b0;font-size:8.5px}.pmg-evidence b{color:#245cab;font-size:9.5px}.pmg-evidence small{color:#6b7684;font-size:9.5px;line-height:1.4}
      .pmg-detail-foot{display:flex;justify-content:space-between;gap:8px;margin-top:8px;color:#9aa4b0;font-size:9px;font-weight:700}.pmg-detail-foot strong{color:#c33243}
      .pmg-more{display:block;width:100%;min-height:42px;margin-top:8px;border:1px solid #dfe3e8;border-radius:11px;background:#fff;color:#4e5968;font:inherit;font-size:11px;font-weight:800;cursor:pointer}
      .pmg-empty{padding:32px 14px;border:1px dashed #dfe4ea;border-radius:12px;color:#8b95a1;text-align:center;font-size:12px}
      @media(max-width:900px){.pmg-row{grid-template-columns:80px minmax(135px,1.3fr) 78px 78px 78px 84px 54px 86px 16px;gap:5px}}
      @media(max-width:700px){
        .app-context-nav[data-app-context="discover"]{grid-template-columns:repeat(3,minmax(0,1fr))!important}
        .app-context-nav[data-app-context="discover"] .app-context-btn{font-size:12px!important;padding:0 3px!important}
        .pmg-head{display:block}.pmg-head h2{font-size:20px}.pmg-head p{font-size:11px}.pmg-date{display:inline-flex;margin-top:7px}
        .pmg-kpis,.pmg-status-strip{grid-template-columns:repeat(2,minmax(0,1fr))}
        .pmg-kpi{padding:10px 11px}.pmg-kpi b{font-size:18px}
        .pmg-policy{align-items:flex-start;flex-direction:column}
        .pmg-tools{grid-template-columns:1fr 1fr}.pmg-search-wrap{grid-column:1/-1}.pmg-tools [data-pmg-sort]{grid-column:1/-1}
        .pmg-list{border-radius:12px}
        .pmg-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;grid-template-areas:'date stock status' 'price price return' 'metrics metrics metrics';gap:5px 8px;min-height:84px;padding:10px 11px}
        .pmg-date-cell{grid-area:date;align-self:start}.pmg-stock{grid-area:stock}.pmg-stock strong{font-size:14px}.pmg-status-cell{grid-area:status;justify-self:end}
        .pmg-entry{grid-area:price;color:#6b7684}.pmg-entry::after{content:' →'}.pmg-current{grid-area:price;margin-left:72px;font-weight:800}
        .pmg-return{grid-area:return;justify-self:end;font-size:15px}.pmg-best{grid-area:metrics;justify-self:end;font-size:9.5px}.pmg-best::before{content:'최고 ';color:#8b95a1;font-weight:650}
        .pmg-score{grid-area:metrics;justify-self:end;margin-right:88px;font-size:9.5px}.pmg-score::before{content:'점수 ';color:#8b95a1;font-weight:650}
        .pmg-chevron{grid-area:return;justify-self:end;align-self:end}
        .pmg-detail-grid{grid-template-columns:1fr}.pmg-detail{padding:10px 11px 12px}
      }`;
    document.head.appendChild(style);
  }

  function statusMeta(status) {
    return STATUS[status] || STATUS.PENDING_REVIEW;
  }

  function recommendations() {
    return Array.isArray(recommendationData?.recommendations) ? recommendationData.recommendations : [];
  }

  function monitorPicks() {
    return Array.isArray(monitorData?.picks) ? monitorData.picks : [];
  }

  function pickKey(date, code, symbol) {
    return `${String(date || '')}:${String(code || String(symbol || '').split('.')[0] || '')}`;
  }

  function monitorFor(row) {
    const key = pickKey(row.recommendedDate, row.code, row.symbol);
    return monitorPicks().find((pick) => String(pick.pickId || pickKey(pick.pickDate, pick.code, pick.symbol)) === key) || null;
  }

  function combinedRows() {
    return recommendations().map((row) => ({ ...row, monitor: monitorFor(row) }));
  }

  function evidenceHtml(pick) {
    const evidence = Array.isArray(pick?.monitor?.evidence) ? pick.monitor.evidence : [];
    if (!evidence.length) return '<p>추천 이후 검증 가능한 신규 근거를 아직 확보하지 못했습니다.</p>';
    return `<div class="pmg-evidence">${evidence.slice(0,4).map((item) => `
      <a href="${esc(item.sourceUrl || '#')}" target="_blank" rel="noopener noreferrer">
        <span>${esc(item.publishedAt || '')}</span>
        <b>${esc(item.sourceTitle || '검증 근거')}</b>
        <small>${esc(item.fact || '')}</small>
      </a>`).join('')}</div>`;
  }

  function filteredRows() {
    let rows = combinedRows();
    if (filters.query) {
      rows = rows.filter((row) => `${row.name || ''} ${row.code || ''} ${row.symbol || ''}`.toLowerCase().includes(filters.query));
    }
    if (filters.performance === 'win') rows = rows.filter((row) => (num(row.returnPct) || 0) > 0);
    if (filters.performance === 'loss') rows = rows.filter((row) => (num(row.returnPct) || 0) < 0);
    if (filters.status !== 'all') rows = rows.filter((row) => (row.monitor?.status || 'PENDING_REVIEW') === filters.status);
    if (filters.period !== 'all' && rows.length) {
      const days = Number(filters.period);
      const cutoff = Date.now() - Math.max(0, days - 1) * 86400000;
      rows = rows.filter((row) => dateValue(row.recommendedDate) >= cutoff);
    }

    const latest = (a,b) => dateValue(b.recommendedDate) - dateValue(a.recommendedDate) || Number(a.rank || 99) - Number(b.rank || 99);
    if (filters.sort === 'return') rows.sort((a,b) => (num(b.returnPct) ?? -Infinity) - (num(a.returnPct) ?? -Infinity) || latest(a,b));
    else if (filters.sort === 'best') rows.sort((a,b) => (num(b.bestReturnPct) ?? -Infinity) - (num(a.bestReturnPct) ?? -Infinity) || latest(a,b));
    else if (filters.sort === 'score') rows.sort((a,b) => (num(b.score) ?? -Infinity) - (num(a.score) ?? -Infinity) || latest(a,b));
    else if (filters.sort === 'status') rows.sort((a,b) => statusMeta(a.monitor?.status).order - statusMeta(b.monitor?.status).order || latest(a,b));
    else rows.sort(latest);
    return rows;
  }

  function cardHtml(row, index) {
    const pick = row.monitor;
    const meta = statusMeta(pick?.status || 'PENDING_REVIEW');
    const id = `pmg-${String(row.recommendedDate || 'date')}-${String(row.code || row.symbol || index)}-${index}`.replace(/[^a-zA-Z0-9_-]/g,'-');
    const thesis = pick?.originalThesis?.summary
      || (Array.isArray(pick?.originalThesis?.pillars) ? pick.originalThesis.pillars.join(' · ') : '')
      || row.reason || '추천 당시 투자논리 기록 없음';
    const reviewReason = pick?.monitor?.reason || '최신 점검 대기';
    const reviewed = pick?.monitor?.lastReviewedTradeDate || String(pick?.monitor?.lastReviewedAt || '').slice(0,10) || '-';
    return `
      <div class="pmg-item">
        <button type="button" class="pmg-row" data-pmg-row="${esc(id)}" aria-expanded="false">
          <span class="pmg-cell pmg-date-cell">${esc(row.recommendedDate || '-')}</span>
          <span class="pmg-cell pmg-stock"><strong>${esc(row.name || row.symbol || '-')}</strong><small>${esc(row.code || String(row.symbol || '').split('.')[0] || '')}</small></span>
          <span class="pmg-cell pmg-entry">${price(row.recommendedPrice)}</span>
          <span class="pmg-cell pmg-current">${price(row.currentPrice)}</span>
          <span class="pmg-cell pmg-return ${returnClass(row.returnPct)}">${pct(row.returnPct)}</span>
          <span class="pmg-cell pmg-best ${returnClass(row.bestReturnPct)}">${pct(row.bestReturnPct)}</span>
          <span class="pmg-cell pmg-score">${num(row.score) == null ? '-' : `${Math.round(num(row.score))}점`}</span>
          <span class="pmg-cell pmg-status-cell"><span class="pmg-status ${meta.cls}">${meta.icon} ${meta.label}</span></span>
          <span class="pmg-chevron" aria-hidden="true">⌄</span>
        </button>
        <div class="pmg-detail" data-pmg-detail="${esc(id)}" hidden>
          <div class="pmg-detail-grid">
            <div class="pmg-block"><strong>추천 당시 이유</strong><p>${esc(row.reason || '추천 사유가 기록되지 않았습니다.')}</p></div>
            <div class="pmg-block"><strong>투자논리 기준선</strong><p>${esc(thesis)}</p></div>
            <div class="pmg-block"><strong>최근 점검</strong><p>${esc(reviewReason)}</p></div>
            <div class="pmg-block"><strong>검증 근거</strong>${evidenceHtml(pick)}</div>
          </div>
          <div class="pmg-detail-foot"><span>마지막 점검 ${esc(reviewed)} · 시세기준 ${esc(row.lastUpdatedTradeDate || '-')}</span>${pick?.needsUserReview ? '<strong>사용자 확인 필요</strong>' : ''}</div>
        </div>
      </div>`;
  }

  function ensurePanel() {
    const tab = document.getElementById('screener-tab');
    if (!tab) return null;
    let panel = document.getElementById('pick-management-direct');
    if (panel) return panel;

    panel = document.createElement('section');
    panel.id = 'pick-management-direct';
    panel.hidden = true;
    panel.innerHTML = `
      <div class="pmg-head">
        <div><span class="pmg-eyebrow">CHARTVIEW PICK</span><h2>PICK 관리</h2><p>누적 추천 성과와 추천 이후 투자논리 점검을 한 화면에서 관리합니다. 종목을 펼치면 추천 사유, 최근 점검, 검증 근거를 함께 확인할 수 있습니다.</p></div>
        <span class="pmg-date" data-pmg-date>데이터 불러오는 중</span>
      </div>
      <div class="pmg-kpis" data-pmg-performance-kpis></div>
      <div class="pmg-status-strip" data-pmg-status-kpis></div>
      <div class="pmg-policy"><span data-pmg-review-date>점검일 확인 중</span><b>매도검토는 자동 매도 확정이 아니며 가격·차트만으로 판정하지 않습니다.</b></div>
      <div class="pmg-tools">
        <label class="pmg-search-wrap"><input class="pmg-input" type="search" data-pmg-query placeholder="종목명 · 코드 검색" autocomplete="off"></label>
        <select class="pmg-select" data-pmg-period aria-label="기간 필터"><option value="all">기간 전체</option><option value="7">최근 7일</option><option value="30">최근 30일</option></select>
        <select class="pmg-select" data-pmg-performance aria-label="성과 필터"><option value="all">성과 전체</option><option value="win">수익 종목</option><option value="loss">손실 종목</option></select>
        <select class="pmg-select" data-pmg-status aria-label="점검 상태 필터"><option value="all">상태 전체</option><option value="SELL_REVIEW">🔴 매도검토</option><option value="WATCH">🟡 경계</option><option value="KEEP">🟢 유지</option><option value="PENDING_REVIEW">⚪ 검토 대기</option><option value="EXIT">종료</option></select>
        <select class="pmg-select" data-pmg-sort aria-label="정렬 기준"><option value="latest">최신 추천순</option><option value="status">점검 우선순</option><option value="return">수익률 높은순</option><option value="best">최고수익률 높은순</option><option value="score">점수 높은순</option></select>
      </div>
      <div class="pmg-summary" data-pmg-summary></div>
      <div class="pmg-list" data-pmg-list><div class="pmg-empty">PICK 데이터를 불러오는 중입니다.</div></div>
      <button type="button" class="pmg-more" data-pmg-more hidden>더 보기</button>`;
    tab.appendChild(panel);

    panel.querySelector('[data-pmg-query]')?.addEventListener('input', (event) => { filters.query = event.currentTarget.value.trim().toLowerCase(); visibleCount = PAGE_SIZE; renderRows(); });
    panel.querySelector('[data-pmg-period]')?.addEventListener('change', (event) => { filters.period = event.currentTarget.value; visibleCount = PAGE_SIZE; renderRows(); });
    panel.querySelector('[data-pmg-performance]')?.addEventListener('change', (event) => { filters.performance = event.currentTarget.value; visibleCount = PAGE_SIZE; renderRows(); });
    panel.querySelector('[data-pmg-status]')?.addEventListener('change', (event) => { filters.status = event.currentTarget.value; visibleCount = PAGE_SIZE; renderRows(); });
    panel.querySelector('[data-pmg-sort]')?.addEventListener('change', (event) => { filters.sort = event.currentTarget.value; visibleCount = PAGE_SIZE; renderRows(); });
    panel.querySelector('[data-pmg-more]')?.addEventListener('click', () => { visibleCount += PAGE_SIZE; renderRows(); });
    panel.addEventListener('click', (event) => {
      const row = event.target.closest('[data-pmg-row]');
      if (!row) return;
      const id = row.dataset.pmgRow;
      const detail = panel.querySelector(`[data-pmg-detail="${CSS.escape(id)}"]`);
      if (!detail) return;
      const willOpen = detail.hidden;
      detail.hidden = !willOpen;
      row.setAttribute('aria-expanded', String(willOpen));
    });
    return panel;
  }

  function renderKpis() {
    const panel = ensurePanel();
    if (!panel) return;
    const rows = recommendations();
    const evaluated = rows.filter((row) => num(row.returnPct) != null);
    const wins = evaluated.filter((row) => num(row.returnPct) > 0).length;
    const avg = evaluated.length ? evaluated.reduce((sum,row) => sum + num(row.returnPct), 0) / evaluated.length : null;
    const dayCount = new Set(rows.map((row) => row.recommendedDate).filter(Boolean)).size;
    const latestClose = rows.reduce((max,row) => String(row.lastUpdatedTradeDate || '') > max ? String(row.lastUpdatedTradeDate || '') : max, '');

    const perf = panel.querySelector('[data-pmg-performance-kpis]');
    if (perf) perf.innerHTML = `
      <div class="pmg-kpi"><span>누적 추천일</span><b>${dayCount}</b></div>
      <div class="pmg-kpi"><span>누적 추천 건수</span><b>${rows.length}</b></div>
      <div class="pmg-kpi"><span>수익 구간 비율</span><b>${evaluated.length ? `${Math.round(wins/evaluated.length*100)}%` : '-'}</b><small>평가 ${evaluated.length}/${rows.length}건</small></div>
      <div class="pmg-kpi"><span>건별 평균 수익률</span><b class="${returnClass(avg)}">${pct(avg)}</b><small>미평가 제외</small></div>`;

    const counts = {KEEP:0,WATCH:0,SELL_REVIEW:0,PENDING_REVIEW:0,EXIT:0};
    monitorPicks().forEach((pick) => { counts[pick.status] = (counts[pick.status] || 0) + 1; });
    const status = panel.querySelector('[data-pmg-status-kpis]');
    if (status) status.innerHTML = `
      <div class="pmg-status-summary keep"><span>🟢 유지</span><b>${counts.KEEP || 0}</b></div>
      <div class="pmg-status-summary watch"><span>🟡 경계</span><b>${counts.WATCH || 0}</b></div>
      <div class="pmg-status-summary sell"><span>🔴 매도검토</span><b>${counts.SELL_REVIEW || 0}</b></div>
      <div class="pmg-status-summary"><span>⚪ 검토 대기</span><b>${counts.PENDING_REVIEW || 0}</b></div>`;

    const date = panel.querySelector('[data-pmg-date]');
    if (date) date.textContent = latestClose ? `${latestClose} 종가 기준` : '시세 기준일 미확인';
    const review = panel.querySelector('[data-pmg-review-date]');
    const updated = monitorData?.reviewSourceUpdated || monitorData?.generatedAt || '';
    if (review) review.textContent = updated ? `사후점검 ${String(updated).slice(0,10)} 기준` : '사후점검 기준일 미확인';
  }

  function renderRows() {
    const panel = ensurePanel();
    if (!panel) return;
    const rows = filteredRows();
    const visible = rows.slice(0, visibleCount);
    const summary = panel.querySelector('[data-pmg-summary]');
    const list = panel.querySelector('[data-pmg-list]');
    const more = panel.querySelector('[data-pmg-more]');
    if (summary) summary.textContent = `${rows.length.toLocaleString('ko-KR')}개 기록 · ${visible.length.toLocaleString('ko-KR')}개 표시`;
    if (list) list.innerHTML = visible.length ? visible.map(cardHtml).join('') : '<div class="pmg-empty">조건에 맞는 PICK 기록이 없습니다.</div>';
    if (more) {
      more.hidden = visible.length >= rows.length;
      more.textContent = `더 보기 · ${Math.min(PAGE_SIZE, rows.length-visible.length).toLocaleString('ko-KR')}개`;
    }
  }

  function render() {
    renderKpis();
    renderRows();
  }

  async function load(force = false) {
    if (!force && monitorData && recommendationData) { render(); return; }
    const stamp = Date.now();
    const [monitorRes, recRes] = await Promise.all([
      fetch(`/static/data/pick_monitor.json?v=${stamp}`, {cache:'no-store'}),
      fetch(`/static/data/ai_recommendations.json?v=${stamp}`, {cache:'no-store'}),
    ]);
    if (!monitorRes.ok) throw new Error(`pick_monitor HTTP ${monitorRes.status}`);
    if (!recRes.ok) throw new Error(`ai_recommendations HTTP ${recRes.status}`);
    monitorData = await monitorRes.json();
    recommendationData = await recRes.json();
    render();
  }

  function setOuterActive(nav, button) {
    nav.querySelectorAll('.app-context-btn').forEach((node) => node.classList.toggle('active', node === button));
  }

  function closeManagement() {
    open = false;
    const tab = document.getElementById('screener-tab');
    const panel = document.getElementById('pick-management-direct');
    tab?.classList.remove('pick-management-active');
    if (panel) panel.hidden = true;
  }

  function openManagement(nav, button) {
    open = true;
    const screenerButton = nav.querySelector('[data-app-tab="screener"]');
    if (screenerButton && !document.getElementById('screener-tab')?.classList.contains('active')) screenerButton.click();
    const panel = ensurePanel();
    const tab = document.getElementById('screener-tab');
    if (!panel || !tab) return;
    tab.classList.add('pick-management-active');
    panel.hidden = false;
    setOuterActive(nav, button);
    window.scrollTo({top:0,behavior:'smooth'});
    load().catch((error) => {
      console.error('[PICK management]', error);
      const list = panel.querySelector('[data-pmg-list]');
      if (list) list.innerHTML = '<div class="pmg-empty">PICK 관리 데이터를 불러오지 못했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.</div>';
    });
  }

  function install() {
    if (installed) return true;
    const nav = document.querySelector('.app-context-nav[data-app-context="discover"]');
    if (!nav) return false;
    addStyle();

    let button = nav.querySelector('[data-pick-monitor-tab]');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'app-context-btn';
      button.dataset.pickMonitorTab = '1';
      nav.appendChild(button);
    }
    button.textContent = 'PICK 관리';
    nav.style.gridTemplateColumns = 'repeat(3,minmax(0,1fr))';

    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      openManagement(nav, button);
    });
    nav.querySelectorAll('[data-app-tab]').forEach((node) => node.addEventListener('click', closeManagement));
    document.querySelectorAll('[data-app-mode]').forEach((node) => {
      if (node.dataset.appMode === 'discover') node.addEventListener('click', closeManagement);
    });

    ensurePanel();
    installed = true;
    return true;
  }

  function boot(attempt = 0) {
    if (install()) return;
    if (attempt < 120) setTimeout(() => boot(attempt + 1), 50);
  }

  window.__PICK_MANAGEMENT_TOP_LEVEL__ = true;
  window.__openPickManagement = () => {
    const nav = document.querySelector('.app-context-nav[data-app-context="discover"]');
    const button = nav?.querySelector('[data-pick-monitor-tab]');
    if (nav && button) openManagement(nav, button);
    else setTimeout(() => window.__openPickManagement?.(), 80);
  };
  window.__openVisiblePickMonitor = window.__openPickManagement;
  window.__openAiPickLedger = window.__openPickManagement;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), {once:true});
  else boot();

  window.__PICK_MONITOR_VISIBLE_TAB_VERSION__ = VERSION;
})();