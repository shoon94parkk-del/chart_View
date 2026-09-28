(() => {
  'use strict';

  const VERSION = '20260928-visible-tab-v1';
  const STATUS = {
    SELL_REVIEW: { label: '매도검토', icon: '🔴', cls: 'sell', order: 0 },
    WATCH: { label: '경계', icon: '🟡', cls: 'watch', order: 1 },
    PENDING_REVIEW: { label: '검토 대기', icon: '⚪', cls: 'pending', order: 2 },
    KEEP: { label: '유지', icon: '🟢', cls: 'keep', order: 3 },
    EXIT: { label: '종료', icon: '✓', cls: 'exit', order: 4 },
  };
  let installed = false;
  let monitorOpen = false;
  let monitorData = null;
  let recommendationData = null;
  let filter = 'all';

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

  function addStyle() {
    if (document.getElementById('pick-monitor-visible-tab-style')) return;
    const style = document.createElement('style');
    style.id = 'pick-monitor-visible-tab-style';
    style.textContent = `
      #screener-tab.pick-monitor-direct-active > :not(#pick-monitor-direct){display:none!important}
      #pick-monitor-direct{padding:2px 0 30px}
      #pick-monitor-direct[hidden]{display:none!important}
      .pmv-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin:0 0 12px}
      .pmv-head h2{margin:0;color:#191f28;font-size:20px;letter-spacing:-.02em}
      .pmv-head p{margin:5px 0 0;color:#8b95a1;font-size:11px;line-height:1.45}
      .pmv-date{flex:0 0 auto;color:#8b95a1;font-size:10px;font-weight:750}
      .pmv-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:0 0 10px}
      .pmv-kpi{padding:10px 11px;border:1px solid #e5e8eb;border-radius:12px;background:#fff}
      .pmv-kpi span{display:block;color:#6b7684;font-size:10px;font-weight:800}
      .pmv-kpi b{display:block;margin-top:2px;color:#191f28;font-size:19px;font-weight:900}
      .pmv-tools{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
      .pmv-select{min-height:38px;padding:0 10px;border:1px solid #dfe3e8;border-radius:10px;background:#fff;color:#333d4b;font-weight:750}
      .pmv-policy{color:#8b95a1;font-size:9.5px;font-weight:700}
      .pmv-list{display:grid;gap:8px}
      .pmv-card{padding:13px;border:1px solid #e5e8eb;border-radius:14px;background:#fff}
      .pmv-card.sell{border-color:#f0cdd1;background:#fffafa}.pmv-card.watch{border-color:#efe2ae;background:#fffdf6}.pmv-card.keep{border-color:#d9ebdf}
      .pmv-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
      .pmv-stock{display:grid;gap:2px;min-width:0}.pmv-stock strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#191f28;font-size:15px}.pmv-stock small{color:#8b95a1;font-size:10px;font-weight:700}
      .pmv-status{flex:0 0 auto;padding:5px 8px;border-radius:999px;font-size:10px;font-weight:900;background:#f2f4f6;color:#6b7684}
      .pmv-status.keep{background:#e8f7ed;color:#24713d}.pmv-status.watch{background:#fff4cc;color:#8a6412}.pmv-status.sell{background:#ffecef;color:#c33243}
      .pmv-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-top:9px;padding:8px 9px;border-radius:10px;background:#f8f9fb}
      .pmv-metrics span{color:#8b95a1;font-size:9px;font-weight:700}.pmv-metrics b{display:block;margin-top:2px;color:#333d4b;font-size:10px}
      .pmv-section{margin-top:9px}.pmv-section>b{display:block;margin-bottom:3px;color:#4e5968;font-size:10px}.pmv-section p{margin:0;color:#59636f;font-size:10.5px;line-height:1.5}
      .pmv-evidence{display:grid;gap:5px}.pmv-evidence a{display:grid;gap:2px;padding:7px 8px;border:1px solid #edf0f3;border-radius:9px;background:#fbfcfe;text-decoration:none}.pmv-evidence strong{color:#245cab;font-size:10px}.pmv-evidence small{color:#6b7684;font-size:9.5px;line-height:1.4}.pmv-evidence span{color:#9aa4b0;font-size:8.5px}
      .pmv-foot{display:flex;justify-content:space-between;gap:8px;margin-top:8px;padding-top:7px;border-top:1px solid #f0f2f4;color:#9aa4b0;font-size:9px;font-weight:700}.pmv-foot strong{color:#c33243}
      .pmv-empty{padding:28px 14px;border:1px dashed #dfe4ea;border-radius:12px;color:#8b95a1;text-align:center;font-size:12px}
      @media(max-width:700px){
        .app-context-nav[data-app-context="discover"]{grid-template-columns:repeat(3,minmax(0,1fr))!important}
        .app-context-nav[data-app-context="discover"] .app-context-btn{font-size:12px!important;padding:0 3px!important}
        .pmv-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
        .pmv-head{display:block}.pmv-date{display:block;margin-top:6px}
        .pmv-tools{align-items:flex-start;flex-direction:column}.pmv-select{width:100%}
        .pmv-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
      }`;
    document.head.appendChild(style);
  }

  function statusMeta(status) {
    return STATUS[status] || STATUS.PENDING_REVIEW;
  }

  function recommendationFor(pick) {
    const rows = Array.isArray(recommendationData?.recommendations) ? recommendationData.recommendations : [];
    return rows.find((row) =>
      String(row.recommendedDate || '') === String(pick.pickDate || '') &&
      String(row.code || String(row.symbol || '').split('.')[0] || '') === String(pick.code || '')
    ) || null;
  }

  function evidenceHtml(pick) {
    const evidence = Array.isArray(pick?.monitor?.evidence) ? pick.monitor.evidence : [];
    if (!evidence.length) return '<p>추천 이후 검증 가능한 신규 근거를 아직 확보하지 못했습니다.</p>';
    return `<div class="pmv-evidence">${evidence.slice(0,4).map((item) => `
      <a href="${esc(item.sourceUrl || '#')}" target="_blank" rel="noopener noreferrer">
        <span>${esc(item.publishedAt || '')}</span>
        <strong>${esc(item.sourceTitle || '검증 근거')}</strong>
        <small>${esc(item.fact || '')}</small>
      </a>`).join('')}</div>`;
  }

  function cardHtml(pick) {
    const meta = statusMeta(pick.status);
    const rec = recommendationFor(pick);
    const thesis = pick?.originalThesis?.summary
      || (Array.isArray(pick?.originalThesis?.pillars) ? pick.originalThesis.pillars.join(' · ') : '')
      || '추천 당시 투자논리 기록 없음';
    const reason = pick?.monitor?.reason || '최신 검토 대기';
    const reviewed = pick?.monitor?.lastReviewedTradeDate || String(pick?.monitor?.lastReviewedAt || '').slice(0,10) || '-';
    return `
      <article class="pmv-card ${meta.cls}">
        <div class="pmv-top">
          <div class="pmv-stock"><strong>${esc(pick.name || pick.symbol || '-')}</strong><small>${esc(pick.code || '')} · ${esc(pick.pickDate || '-')} PICK</small></div>
          <span class="pmv-status ${meta.cls}">${meta.icon} ${meta.label}</span>
        </div>
        <div class="pmv-metrics">
          <span>추천가<b>${price(pick.pickPrice)}</b></span>
          <span>최근가<b>${price(rec?.currentPrice)}</b></span>
          <span>수익률<b>${pct(rec?.returnPct)}</b></span>
          <span>시세기준<b>${esc(rec?.lastUpdatedTradeDate || '-')}</b></span>
        </div>
        <div class="pmv-section"><b>추천 당시 논리</b><p>${esc(thesis)}</p></div>
        <div class="pmv-section"><b>최근 점검</b><p>${esc(reason)}</p></div>
        <div class="pmv-section"><b>검증 근거</b>${evidenceHtml(pick)}</div>
        <div class="pmv-foot"><span>마지막 검토 ${esc(reviewed)}</span>${pick.needsUserReview ? '<strong>사용자 확인 필요</strong>' : ''}</div>
      </article>`;
  }

  function ensurePanel() {
    const tab = document.getElementById('screener-tab');
    if (!tab) return null;
    let panel = document.getElementById('pick-monitor-direct');
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'pick-monitor-direct';
      panel.hidden = true;
      panel.innerHTML = `
        <div class="pmv-head">
          <div><h2>기존 PICK 점검</h2><p>추천 당시 투자논리와 최신 검증 근거를 비교합니다. 매도검토는 자동 매도 확정이 아닙니다.</p></div>
          <span class="pmv-date" data-pmv-date>점검 데이터 불러오는 중</span>
        </div>
        <div class="pmv-kpis" data-pmv-kpis></div>
        <div class="pmv-tools">
          <select class="pmv-select" data-pmv-filter aria-label="PICK 상태 필터">
            <option value="all">상태 전체</option>
            <option value="SELL_REVIEW">🔴 매도검토</option>
            <option value="WATCH">🟡 경계</option>
            <option value="KEEP">🟢 유지</option>
            <option value="PENDING_REVIEW">⚪ 검토 대기</option>
            <option value="EXIT">종료</option>
          </select>
          <span class="pmv-policy">가격·차트만으로 매도검토하지 않음</span>
        </div>
        <div class="pmv-list" data-pmv-list><div class="pmv-empty">PICK 점검 데이터를 불러오는 중입니다.</div></div>`;
      tab.appendChild(panel);
      panel.querySelector('[data-pmv-filter]')?.addEventListener('change', (event) => {
        filter = event.currentTarget.value;
        render();
      });
    }
    return panel;
  }

  function render() {
    const panel = ensurePanel();
    if (!panel) return;
    const picks = Array.isArray(monitorData?.picks) ? monitorData.picks : [];
    const counts = {KEEP:0, WATCH:0, SELL_REVIEW:0, PENDING_REVIEW:0, EXIT:0};
    picks.forEach((pick) => { counts[pick.status] = (counts[pick.status] || 0) + 1; });

    const kpis = panel.querySelector('[data-pmv-kpis]');
    if (kpis) kpis.innerHTML = `
      <div class="pmv-kpi"><span>🟢 유지</span><b>${counts.KEEP || 0}</b></div>
      <div class="pmv-kpi"><span>🟡 경계</span><b>${counts.WATCH || 0}</b></div>
      <div class="pmv-kpi"><span>🔴 매도검토</span><b>${counts.SELL_REVIEW || 0}</b></div>
      <div class="pmv-kpi"><span>⚪ 검토 대기</span><b>${counts.PENDING_REVIEW || 0}</b></div>`;

    const date = panel.querySelector('[data-pmv-date]');
    if (date) {
      const updated = monitorData?.reviewSourceUpdated || monitorData?.generatedAt || '';
      date.textContent = updated ? `${String(updated).slice(0,10)} 점검 기준` : '점검일 미확인';
    }

    const rows = picks
      .filter((pick) => filter === 'all' || pick.status === filter)
      .sort((a,b) => statusMeta(a.status).order - statusMeta(b.status).order
        || String(b.pickDate || '').localeCompare(String(a.pickDate || ''))
        || Number(a.rank || 99) - Number(b.rank || 99));
    const list = panel.querySelector('[data-pmv-list]');
    if (!list) return;
    list.innerHTML = rows.length ? rows.map(cardHtml).join('') : '<div class="pmv-empty">해당 상태의 PICK이 없습니다.</div>';
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

  function closeMonitor() {
    monitorOpen = false;
    const tab = document.getElementById('screener-tab');
    const panel = document.getElementById('pick-monitor-direct');
    tab?.classList.remove('pick-monitor-direct-active');
    if (panel) panel.hidden = true;
  }

  function openMonitor(nav, button) {
    monitorOpen = true;
    const screenerButton = nav.querySelector('[data-app-tab="screener"]');
    if (screenerButton && !document.getElementById('screener-tab')?.classList.contains('active')) screenerButton.click();
    const panel = ensurePanel();
    const tab = document.getElementById('screener-tab');
    if (!panel || !tab) return;
    tab.classList.add('pick-monitor-direct-active');
    panel.hidden = false;
    setOuterActive(nav, button);
    window.scrollTo({top:0, behavior:'smooth'});
    load().catch((error) => {
      console.error('[PICK monitor visible tab]', error);
      const list = panel.querySelector('[data-pmv-list]');
      if (list) list.innerHTML = '<div class="pmv-empty">PICK 점검 데이터를 불러오지 못했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.</div>';
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
      button.textContent = 'PICK 점검';
      nav.appendChild(button);
    }
    nav.style.gridTemplateColumns = 'repeat(3,minmax(0,1fr))';

    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      openMonitor(nav, button);
    });

    nav.querySelectorAll('[data-app-tab]').forEach((node) => node.addEventListener('click', closeMonitor));
    document.querySelectorAll('[data-app-mode]').forEach((node) => {
      if (node.dataset.appMode === 'discover') node.addEventListener('click', closeMonitor);
    });

    ensurePanel();
    installed = true;
    return true;
  }

  function boot(attempt = 0) {
    if (install()) return;
    if (attempt < 120) setTimeout(() => boot(attempt + 1), 50);
  }

  window.__openVisiblePickMonitor = () => {
    const nav = document.querySelector('.app-context-nav[data-app-context="discover"]');
    const button = nav?.querySelector('[data-pick-monitor-tab]');
    if (nav && button) openMonitor(nav, button);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), {once:true});
  else boot();

  window.__PICK_MONITOR_VISIBLE_TAB_VERSION__ = VERSION;
})();
