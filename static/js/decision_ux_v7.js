(() => {
  'use strict';

  let sourcePromise = null;
  let injectionBusy = false;

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const num = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  const pct = (value, digits = 1) => {
    const n = num(value);
    if (n === null) return '-';
    return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
  };

  function revisionPct(current, previous) {
    const a = num(current);
    const b = num(previous);
    if (a === null || b === null || a <= 0 || b <= 0) return null;
    return (a / b - 1) * 100;
  }

  function simplifyValuationNavigation() {
    const section = document.querySelector('#fwdper-tab .metric-section');
    const chips = section?.querySelector('.metric-chips');
    if (!section || !chips) return false;

    const keep = new Set(['overview', 'bands', 'consensus']);
    chips.querySelectorAll('.metric-chip').forEach((button) => {
      if (!keep.has(button.dataset.metric)) button.remove();
    });

    const labels = {
      overview: '종합 비교',
      bands: '역사적 밸류',
      consensus: '실적 컨센서스',
    };
    chips.querySelectorAll('.metric-chip').forEach((button) => {
      const label = labels[button.dataset.metric];
      if (label) button.textContent = label;
    });

    const label = section.querySelector('.metric-label');
    if (label) label.textContent = '밸류에이션 보기';
    section.classList.add('decision-valuation-nav');
    return true;
  }

  function renameRevisionTab() {
    const button = document.querySelector('[data-app-tab="revision"]');
    if (!button) return false;
    button.textContent = '실적·괴리';
    return true;
  }

  function marketOf(symbol) {
    return /\.(KS|KQ)$/.test(symbol) ? 'KR' : 'US';
  }

  function loadSources() {
    if (!sourcePromise) {
      sourcePromise = Promise.all([
        fetch('/static/data/consensus_cache.json', { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`consensus HTTP ${r.status}`);
          return r.json();
        }),
        fetch('/static/data/screener.json', { cache: 'force-cache' })
          .then((r) => r.ok ? r.json() : { stocks: [] })
          .catch(() => ({ stocks: [] })),
      ]);
    }
    return sourcePromise;
  }

  function buildRows(consensus, screener) {
    const localNames = new Map((screener.stocks || []).map((row) => [row.symbol, row.name]));
    return Object.entries(consensus.quotes || {}).map(([symbol, quote]) => {
      const yearly = (quote.periods || {})['0y'] || {};
      const trend = yearly.epsTrend || {};
      const revisions = yearly.revisions || {};
      const prices = quote.priceTrend || {};
      const current = num(trend.current ?? (yearly.earnings || {}).avg);
      const eps30 = revisionPct(current, trend['30daysAgo']);
      const eps90 = revisionPct(current, trend['90daysAgo']);
      const price30 = num(prices.return30);
      const price90 = num(prices.return90);
      const analysts = num((yearly.earnings || {}).analysts) || 0;
      const up30 = num(revisions.up30) || 0;
      const down30 = num(revisions.down30) || 0;
      const balance = up30 - down30;
      return {
        symbol,
        name: localNames.get(symbol) || quote.name || symbol,
        market: marketOf(symbol),
        eps30,
        eps90,
        price30,
        price90,
        gap30: eps30 !== null && price30 !== null ? eps30 - price30 : null,
        gap90: eps90 !== null && price90 !== null ? eps90 - price90 : null,
        analysts,
        balance,
        asOf: prices.asOf || '-',
      };
    });
  }

  function gapCandidates(rows, market) {
    return rows
      .filter((row) => row.market === market
        && row.eps30 !== null && row.eps30 > 0
        && row.price30 !== null && row.gap30 !== null && row.gap30 > 0
        && row.analysts >= 2 && row.balance >= 0)
      .sort((a, b) => (b.gap30 - a.gap30) || (b.eps30 - a.eps30))
      .slice(0, 3);
  }

  function badge(row) {
    if (row.gap30 >= 10 && row.eps30 >= 2 && row.balance > 0) return ['strong', '괴리 큼'];
    if (row.gap30 >= 5) return ['up', '미반영'];
    return ['neutral', '관찰'];
  }

  function gapCard(row) {
    const [key, label] = badge(row);
    return `
      <article class="revision-gap-card">
        <div class="revision-card-top">
          <div>
            <strong class="revision-name">${esc(row.name)}</strong>
            <span class="revision-symbol">${esc(row.symbol)} · ${row.market === 'KR' ? '한국' : '미국'}</span>
          </div>
          <span class="revision-badge ${key}">${label}</span>
        </div>
        <div class="revision-gap-metrics">
          <div><span>EPS 30D</span><strong class="revision-up">${pct(row.eps30)}</strong></div>
          <div><span>주가 30D</span><strong class="${(row.price30 || 0) >= 0 ? 'revision-up' : 'revision-down'}">${pct(row.price30)}</strong></div>
          <div class="revision-gap-highlight"><span>괴리</span><strong>${pct(row.gap30)}</strong></div>
          <div><span>90D 괴리</span><strong>${pct(row.gap90)}</strong></div>
        </div>
        <div class="revision-foot">
          <span>상향-하향 의견 ${row.balance >= 0 ? '+' : ''}${Math.round(row.balance)} · 가격 ${esc(row.asOf)} 기준</span>
          <button class="revision-analyze revision-gap-analyze" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}" type="button">분석하기</button>
        </div>
      </article>`;
  }

  function bindGapActions(panel) {
    panel.querySelectorAll('.revision-gap-analyze').forEach((button) => {
      button.addEventListener('click', () => {
        if (typeof window.addGlobalTicker === 'function') {
          window.addGlobalTicker(button.dataset.symbol, button.dataset.name);
        }
        const ideasButton = document.querySelector('.tab-nav [data-tab="ideas"]');
        if (ideasButton) ideasButton.click();
        else if (typeof window.switchTab === 'function') window.switchTab('fwdper');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  async function injectGapPanel() {
    const root = document.getElementById('revision-radar-body');
    if (!root || root.querySelector('.revision-gap-panel') || injectionBusy) return;
    if (root.querySelector('.revision-loading') || !root.querySelector('.revision-summary')) return;

    injectionBusy = true;
    try {
      const [consensus, screener] = await loadSources();
      if (!document.body.contains(root) || root.querySelector('.revision-gap-panel')) return;
      const rows = buildRows(consensus, screener);
      const kr = gapCandidates(rows, 'KR');
      const us = gapCandidates(rows, 'US');
      const combined = [...kr, ...us];
      const ready = rows.filter((row) => row.eps30 !== null && row.price30 !== null).length;

      const panel = document.createElement('section');
      panel.className = 'revision-gap-panel';
      panel.innerHTML = `
        <div class="revision-gap-head">
          <div>
            <h3>🎯 실적 상향 + 주가 미반영</h3>
            <p>올해 EPS 컨센서스는 올라가는데 같은 30일 동안 주가 반응이 더 약한 종목입니다.</p>
          </div>
          <span class="revision-gap-count">${combined.length}개 표시 · ${ready}개 비교 가능</span>
        </div>
        ${combined.length
          ? `<div class="revision-gap-grid">${combined.map(gapCard).join('')}</div>`
          : '<div class="revision-empty">현재 조건에서 뚜렷한 미반영 후보가 없습니다.</div>'}
        <div class="revision-gap-note">괴리 = EPS 30일 변화율 − 조정주가 30일 수익률. 수치가 클수록 실적 기대 개선에 비해 주가 반응이 약했다는 뜻이며, 악재로 주가가 하락한 경우도 있으므로 매수점수가 아니라 추가 확인용 후보입니다.</div>`;
      root.insertBefore(panel, root.firstChild);
      bindGapActions(panel);
    } catch (error) {
      console.error('Revision-price divergence panel failed:', error);
    } finally {
      injectionBusy = false;
    }
  }

  function setupObservers() {
    const metricChips = document.querySelector('#fwdper-tab .metric-chips');
    if (metricChips && !metricChips.dataset.decisionObserver) {
      metricChips.dataset.decisionObserver = '1';
      new MutationObserver(simplifyValuationNavigation).observe(metricChips, { childList: true });
    }

    const radar = document.getElementById('revision-radar-body');
    if (radar && !radar.dataset.gapObserver) {
      radar.dataset.gapObserver = '1';
      new MutationObserver(() => setTimeout(injectGapPanel, 0)).observe(radar, { childList: true, subtree: false });
    }
  }

  function refresh() {
    simplifyValuationNavigation();
    renameRevisionTab();
    setupObservers();
    injectGapPanel();
  }

  function init() {
    refresh();
    let attempts = 0;
    const timer = setInterval(() => {
      refresh();
      attempts += 1;
      if (attempts >= 30) clearInterval(timer);
    }, 200);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
