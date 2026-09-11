(() => {
  'use strict';

  let cachePromise = null;
  let currentPeriod = '0y';

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const asNum = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  const pct = (value, digits = 1) => {
    const n = asNum(value);
    if (n === null) return '-';
    return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
  };

  function changePct(current, previous) {
    const a = asNum(current);
    const b = asNum(previous);
    // Percentage revisions are only comparable while both estimates are positive.
    // Crossing zero (loss -> profit or vice versa) makes a ratio misleading.
    if (a === null || b === null || a <= 0 || b <= 0) return null;
    return (a / b - 1) * 100;
  }

  function marketOf(symbol) {
    return /\.(KS|KQ)$/.test(symbol) ? 'KR' : 'US';
  }

  function classify(eps30, balance) {
    if (eps30 !== null && eps30 >= 3 && balance > 0) return { key: 'strong', label: '강한 상향' };
    if (eps30 !== null && eps30 > 0 && balance >= 0) return { key: 'up', label: '상향' };
    if (eps30 !== null && eps30 <= -3 && balance < 0) return { key: 'down', label: '하향 주의' };
    return { key: 'neutral', label: '중립' };
  }

  function enrich(symbol, quote, localNames) {
    const row = (quote.periods || {})[currentPeriod] || {};
    const earnings = row.earnings || {};
    const trend = row.epsTrend || {};
    const revisions = row.revisions || {};
    const revenue = row.revenue || {};
    const current = asNum(trend.current ?? earnings.avg);
    const eps7 = changePct(current, trend['7daysAgo']);
    const eps30 = changePct(current, trend['30daysAgo']);
    const eps90 = changePct(current, trend['90daysAgo']);
    const up30 = asNum(revisions.up30) || 0;
    const down30 = asNum(revisions.down30) || 0;
    const balance = up30 - down30;
    const analysts = asNum(earnings.analysts);
    const signal = classify(eps30, balance);
    const accelerating = eps7 !== null && eps30 !== null && eps7 > 0.3 && eps30 > 0;

    return {
      symbol,
      name: localNames.get(symbol) || quote.name || symbol,
      market: marketOf(symbol),
      endDate: row.endDate || '-',
      eps30,
      eps90,
      eps7,
      up30,
      down30,
      balance,
      analysts,
      epsGrowth: asNum(earnings.growth) === null ? null : asNum(earnings.growth) * 100,
      revenueGrowth: asNum(revenue.growth) === null ? null : asNum(revenue.growth) * 100,
      signal,
      accelerating,
    };
  }

  function signalRank(row) {
    return row.signal.key === 'strong' ? 3 : row.signal.key === 'up' ? 2 : row.signal.key === 'neutral' ? 1 : 0;
  }

  function sortRows(rows) {
    return [...rows].sort((a, b) => {
      const signalDiff = signalRank(b) - signalRank(a);
      if (signalDiff) return signalDiff;
      const epsDiff = (b.eps30 ?? -Infinity) - (a.eps30 ?? -Infinity);
      if (epsDiff) return epsDiff;
      return b.balance - a.balance;
    });
  }

  function candidateRows(rows, market) {
    const all = sortRows(rows.filter((row) => row.market === market && row.eps30 !== null && (row.analysts || 0) >= 2));
    const positives = all.filter((row) => row.signal.key === 'strong' || row.signal.key === 'up');
    return (positives.length ? positives : all).slice(0, 6);
  }

  function card(row) {
    const balanceText = `${Math.round(row.up30)}↑ / ${Math.round(row.down30)}↓`;
    return `
      <article class="revision-card" data-revision-signal="${row.signal.key}">
        <div class="revision-card-top">
          <div>
            <strong class="revision-name">${esc(row.name)}</strong>
            <span class="revision-symbol">${esc(row.symbol)}</span>
          </div>
          <span class="revision-badge ${row.signal.key}">${row.signal.label}</span>
        </div>
        <div class="revision-main">
          <div><span>EPS 30일 변화</span><strong class="${(row.eps30 || 0) >= 0 ? 'revision-up' : 'revision-down'}">${pct(row.eps30)}</strong></div>
          <div><span>EPS 90일 변화</span><strong>${pct(row.eps90)}</strong></div>
          <div><span>30일 의견</span><strong>${balanceText}</strong></div>
          <div><span>EPS 성장률</span><strong>${pct(row.epsGrowth)}</strong></div>
        </div>
        <div class="revision-foot">
          <span>${row.accelerating ? '⚡ 최근 7일 상향 가속 · ' : ''}매출 성장 ${pct(row.revenueGrowth)} · ${Math.round(row.analysts || 0)}명 · ${esc(row.endDate)}</span>
          <button class="revision-analyze" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}" type="button">분석하기</button>
        </div>
      </article>`;
  }

  function section(title, rows, emptyText) {
    return `
      <section class="revision-market-block">
        <div class="revision-market-title">${title}</div>
        ${rows.length
          ? `<div class="revision-grid">${rows.map(card).join('')}</div>`
          : `<div class="revision-empty">${emptyText}</div>`}
      </section>`;
  }

  function bindActions(root) {
    root.querySelectorAll('.revision-analyze').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.symbol;
        const name = button.dataset.name;
        if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
        const ideasButton = document.querySelector('.tab-nav [data-tab="ideas"]');
        if (ideasButton) ideasButton.click();
        else if (typeof window.switchTab === 'function') window.switchTab('fwdper');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  async function loadSource() {
    if (!cachePromise) {
      cachePromise = Promise.all([
        fetch('/static/data/consensus_cache.json', { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`consensus HTTP ${r.status}`);
          return r.json();
        }),
        fetch('/static/data/screener.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : { stocks: [] }).catch(() => ({ stocks: [] })),
      ]);
    }
    return cachePromise;
  }

  async function render() {
    const root = document.getElementById('revision-radar-body');
    if (!root) return;
    root.innerHTML = '<div class="revision-loading"><div class="spinner"></div><span>실적 컨센서스를 정리하는 중...</span></div>';

    try {
      const [consensus, screener] = await loadSource();
      const quotes = consensus.quotes || {};
      const localNames = new Map((screener.stocks || []).map((row) => [row.symbol, row.name]));
      const rows = Object.entries(quotes)
        .map(([symbol, quote]) => enrich(symbol, quote, localNames))
        .filter((row) => row.eps30 !== null);

      const strong = rows.filter((row) => row.signal.key === 'strong').length;
      const up = rows.filter((row) => row.signal.key === 'up').length;
      const down = rows.filter((row) => row.signal.key === 'down').length;
      const kr = candidateRows(rows, 'KR');
      const us = candidateRows(rows, 'US');

      root.innerHTML = `
        <div class="revision-summary">
          <div><span>강한 상향</span><strong>${strong}</strong></div>
          <div><span>상향</span><strong>${up}</strong></div>
          <div><span>하향 주의</span><strong>${down}</strong></div>
          <div><span>분석 가능</span><strong>${rows.length}</strong></div>
        </div>
        <div class="revision-method">정렬 기준: 강한 상향 → EPS 30일 변화율 → 상향·하향 의견 차이. 적자↔흑자처럼 EPS가 0을 가로지르는 구간은 왜곡을 막기 위해 순위에서 제외합니다. 숨은 매수점수는 사용하지 않습니다.</div>
        ${section('🇰🇷 한국 상향 후보', kr, '현재 조건에서 한국 상향 후보가 없습니다.')}
        ${section('🇺🇸 미국 상향 후보', us, '현재 조건에서 미국 상향 후보가 없습니다.')}
        <div class="revision-source">Yahoo Finance earningsTrend · 현재 컨센서스 캐시 ${Object.keys(quotes).length}종목 · ${esc(String(consensus.generatedAt || '').slice(0, 10))} 갱신</div>`;
      bindActions(root);
    } catch (error) {
      console.error('Revision radar failed:', error);
      root.innerHTML = '<div class="revision-empty">실적 컨센서스 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
    }
  }

  function install() {
    if (document.getElementById('revision-tab')) return;
    const tab = document.createElement('div');
    tab.id = 'revision-tab';
    tab.className = 'tab-content';
    tab.innerHTML = `
      <section class="revision-section">
        <div class="revision-head">
          <div>
            <h2>🚀 실적 추정치 상향 레이더</h2>
            <p>애널리스트 EPS 추정치가 실제로 올라가는 종목을 자동으로 먼저 보여줍니다.</p>
          </div>
          <div class="revision-period" role="group" aria-label="컨센서스 기간">
            <button type="button" class="revision-period-btn active" data-revision-period="0y">올해</button>
            <button type="button" class="revision-period-btn" data-revision-period="+1y">내년</button>
          </div>
        </div>
        <div id="revision-radar-body"><div class="revision-empty">실적 상향 탭을 열면 데이터를 불러옵니다.</div></div>
      </section>`;

    const screener = document.getElementById('screener-tab');
    if (screener) screener.insertAdjacentElement('afterend', tab);
    else document.getElementById('app')?.appendChild(tab);

    tab.querySelectorAll('[data-revision-period]').forEach((button) => {
      button.addEventListener('click', () => {
        tab.querySelectorAll('[data-revision-period]').forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
        currentPeriod = button.dataset.revisionPeriod;
        render();
      });
    });
  }

  window.__loadRevisionRadar = render;

  function init() {
    install();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
