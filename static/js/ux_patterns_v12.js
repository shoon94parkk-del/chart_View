(() => {
  'use strict';

  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
  const textNum = (value) => {
    const m = String(value || '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : null;
  };
  const shortDate = (value) => {
    if (!value) return '-';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
    return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  };

  function installFilterSheet() {
    const section = qs('.screener-section');
    const row = qs('.screener-main-row', section || document);
    const search = qs('#screener-search');
    const valueSelect = qs('#screener-value');
    const sortSelect = qs('#screener-sort');
    if (!section || !row || !search || !valueSelect || !sortSelect || qs('#ux12-filter-sheet')) return false;

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'ux12-filter-trigger';
    trigger.innerHTML = '<span>필터·정렬</span><b id="ux12-filter-count">0</b>';
    row.appendChild(trigger);

    const backdrop = document.createElement('button');
    backdrop.type = 'button';
    backdrop.className = 'ux12-sheet-backdrop';
    backdrop.setAttribute('aria-label', '필터 닫기');

    const sheet = document.createElement('section');
    sheet.id = 'ux12-filter-sheet';
    sheet.className = 'ux12-filter-sheet';
    sheet.setAttribute('aria-hidden', 'true');
    sheet.innerHTML = `
      <div class="ux12-sheet-handle"></div>
      <div class="ux12-sheet-head"><div><span>FILTER</span><strong>필터·정렬</strong></div><button type="button" data-ux12-close>완료</button></div>
      <div class="ux12-sheet-body">
        <label><span>최소 평균 거래대금</span><select data-ux12-value class="screen-select"></select></label>
        <label><span>정렬 기준</span><select data-ux12-sort class="screen-select"></select></label>
        <p>시장과 투자 아이디어 조건은 위 칩에서 바로 바꿀 수 있습니다.</p>
      </div>`;
    document.body.append(backdrop, sheet);

    const mobileValue = qs('[data-ux12-value]', sheet);
    const mobileSort = qs('[data-ux12-sort]', sheet);
    mobileValue.innerHTML = valueSelect.innerHTML;
    mobileSort.innerHTML = sortSelect.innerHTML;

    const syncFromOriginal = () => {
      mobileValue.value = valueSelect.value;
      mobileSort.value = sortSelect.value;
      const count = Number(valueSelect.value !== '1000000000') + Number(sortSelect.value !== 'score');
      const badge = qs('#ux12-filter-count');
      if (badge) badge.textContent = String(count);
      trigger.classList.toggle('has-filter', count > 0);
    };
    const emit = (target, source) => {
      target.value = source.value;
      target.dispatchEvent(new Event('change', { bubbles: true }));
      syncFromOriginal();
    };
    mobileValue.addEventListener('change', () => emit(valueSelect, mobileValue));
    mobileSort.addEventListener('change', () => emit(sortSelect, mobileSort));
    valueSelect.addEventListener('change', syncFromOriginal);
    sortSelect.addEventListener('change', syncFromOriginal);

    const setOpen = (open) => {
      document.body.classList.toggle('ux12-sheet-open', open);
      sheet.setAttribute('aria-hidden', String(!open));
      if (open) syncFromOriginal();
    };
    trigger.addEventListener('click', () => setOpen(true));
    backdrop.addEventListener('click', () => setOpen(false));
    qs('[data-ux12-close]', sheet).addEventListener('click', () => setOpen(false));
    window.addEventListener('keydown', (event) => { if (event.key === 'Escape') setOpen(false); });
    syncFromOriginal();
    return true;
  }

  function installScreenerKpis() {
    const summary = qs('#screener-summary');
    const results = qs('#screener-results');
    if (!summary || !results) return false;
    let strip = qs('#ux12-screener-kpis');
    if (!strip) {
      strip = document.createElement('div');
      strip.id = 'ux12-screener-kpis';
      strip.className = 'ux12-screener-kpis';
      summary.insertAdjacentElement('afterend', strip);
    }

    const render = () => {
      const rows = qsa('tbody tr', results);
      const total = textNum(summary.textContent) || rows.length;
      const daily = rows.map((r) => textNum(qs('td[data-label="현재가"] div:last-child', r)?.textContent)).filter(Number.isFinite);
      const rsi = rows.map((r) => textNum(qs('td[data-label="RSI"]', r)?.textContent)).filter(Number.isFinite);
      const volume = rows.map((r) => textNum(qs('td[data-label="거래량"]', r)?.textContent)).filter(Number.isFinite);
      const upRate = daily.length ? Math.round(daily.filter((x) => x > 0).length / daily.length * 100) : null;
      const avgRsi = rsi.length ? rsi.reduce((a, b) => a + b, 0) / rsi.length : null;
      const volume2x = volume.filter((x) => x >= 2).length;
      strip.innerHTML = `
        <div><span>조건 일치</span><strong>${total.toLocaleString('ko-KR')}</strong></div>
        <div><span>상승 비율</span><strong>${upRate === null ? '-' : `${upRate}%`}</strong></div>
        <div><span>평균 RSI</span><strong>${avgRsi === null ? '-' : avgRsi.toFixed(1)}</strong></div>
        <div><span>거래량 2x+</span><strong>${volume2x.toLocaleString('ko-KR')}</strong></div>`;
    };
    render();
    new MutationObserver(render).observe(results, { childList: true, subtree: true });
    new MutationObserver(render).observe(summary, { childList: true, characterData: true, subtree: true });
    return true;
  }

  async function installDataStatus() {
    const market = qs('#home-market-v9');
    if (!market) return false;
    let strip = qs('#ux12-data-status');
    if (!strip) {
      strip = document.createElement('section');
      strip.id = 'ux12-data-status';
      strip.className = 'ux12-data-status';
      strip.innerHTML = `
        <div class="ux12-status-head"><span>DATA STATUS</span><strong>데이터 상태</strong><small>소스별 갱신 시점을 한눈에 확인</small></div>
        <div class="ux12-status-grid">
          <div data-status="market"><i></i><span>시장</span><strong>확인 중</strong></div>
          <div data-status="screener"><i></i><span>스크리너</span><strong>확인 중</strong></div>
          <div data-status="consensus"><i></i><span>컨센서스</span><strong>확인 중</strong></div>
          <div data-status="macro"><i></i><span>매크로</span><strong>확인 중</strong></div>
        </div>`;
      market.insertAdjacentElement('afterend', strip);
    }

    const set = (key, label, level = 'ok') => {
      const node = qs(`[data-status="${key}"]`, strip);
      if (!node) return;
      node.classList.remove('ok', 'warn', 'bad');
      node.classList.add(level);
      const strong = qs('strong', node);
      if (strong) strong.textContent = label;
    };

    const marketTime = qs('#home-market-v9-time')?.textContent?.trim();
    set('market', marketTime && !marketTime.includes('불러오는') ? marketTime.replace(' 기준', '') : '최신 시세', marketTime?.includes('확인 필요') ? 'warn' : 'ok');

    const [screener, consensus, macro] = await Promise.all([
      fetch('/static/data/screener.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch('/static/data/consensus_cache.json', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch('/api/macro', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null).catch(() => null),
    ]);
    if (screener) set('screener', `장마감 ${shortDate(screener.tradeDate || screener.updated)}`, 'ok'); else set('screener', '확인 필요', 'warn');
    if (consensus) set('consensus', `${shortDate(consensus.generatedAt)} · ${Number(consensus.count || 0)}종목`, 'ok'); else set('consensus', '확인 필요', 'warn');
    if (macro) set('macro', `${shortDate(macro.generatedAt)} · ${Number(macro.staleCount || 0) ? '일부 지연' : '정상'}`, Number(macro.staleCount || 0) ? 'warn' : 'ok'); else set('macro', '확인 필요', 'warn');
    return true;
  }

  function boot() {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      installFilterSheet();
      installScreenerKpis();
      installDataStatus();
      if (attempts >= 60) clearInterval(timer);
    }, 250);
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(installDataStatus, 350);
      if (event.target.closest('[data-tab="screener"], [data-app-mode="discover"]')) setTimeout(() => { installFilterSheet(); installScreenerKpis(); }, 250);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
