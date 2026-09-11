(() => {
  'use strict';

  const bandCache = new Map();
  let enhanceSeq = 0;

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const num = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const x = Number(value);
    return Number.isFinite(x) ? x : null;
  };
  const clamp = (value, lo = 0, hi = 100) => Math.min(hi, Math.max(lo, Number(value) || 0));
  const pct = (value, digits = 1) => {
    const x = num(value);
    return x === null ? '-' : `${x > 0 ? '+' : ''}${x.toFixed(digits)}%`;
  };
  const revisionPct = (current, previous) => {
    const a = num(current), b = num(previous);
    if (a === null || b === null || a <= 0 || b <= 0) return null;
    return (a / b - 1) * 100;
  };

  function fallbackValuationScore(forwardPE) {
    const pe = num(forwardPE);
    if (pe === null || pe <= 0) return 50;
    if (pe <= 10) return 92;
    if (pe <= 15) return 82;
    if (pe <= 22) return 70;
    if (pe <= 30) return 55;
    if (pe <= 40) return 40;
    return 25;
  }

  function breadthScore(up, down, analysts) {
    const u = Math.max(0, num(up) || 0);
    const d = Math.max(0, num(down) || 0);
    const changed = u + d;
    if (!changed) return 50;
    const directional = (u / changed) * 100;
    const coverage = Math.min(1, changed / Math.max(2, Math.min(num(analysts) || 2, 6)));
    return clamp(50 + (directional - 50) * coverage);
  }

  function trendScore(row) {
    const technical = num(row.techScore);
    if (technical !== null) {
      let score = technical;
      if (row.aligned) score += 8;
      else if (row.cross20) score += 4;
      if (num(row.rsi) !== null && row.rsi > 72) score -= 15;
      return clamp(score);
    }
    const p30 = num(row.price30);
    return p30 === null ? 50 : clamp(50 + p30 * 1.6, 15, 90);
  }

  function computeScore(row) {
    const epsScore = clamp((Math.max(0, row.eps30 || 0) / 15) * 100);
    const breadth = breadthScore(row.up30, row.down30, row.analysts);
    const underreaction = clamp((Math.max(0, row.gap || 0) / 15) * 100);
    const valuation = row.perPercentile !== null && row.perPercentile !== undefined
      ? clamp(100 - row.perPercentile)
      : fallbackValuationScore(row.forwardPE);
    const trend = trendScore(row);
    const total = epsScore * 0.30 + breadth * 0.15 + underreaction * 0.20 + valuation * 0.20 + trend * 0.15;
    return { epsScore, breadth, underreaction, valuation, trend, total };
  }

  function buildRows(consensus, screener, valuation) {
    const names = new Map((screener.stocks || []).map((x) => [x.symbol, x.name]));
    const tech = new Map((screener.stocks || []).map((x) => [x.symbol, x]));
    const quotes = valuation.quotes || {};
    return Object.entries(consensus.quotes || {}).map(([symbol, quote]) => {
      const period = (quote.periods || {})['0y'] || {};
      const trend = period.epsTrend || {};
      const revisions = period.revisions || {};
      const eps30 = revisionPct(trend.current ?? (period.earnings || {}).avg, trend['30daysAgo']);
      const price30 = num((quote.priceTrend || {}).return30);
      const tr = tech.get(symbol) || {};
      const val = quotes[symbol] || {};
      const up30 = num(revisions.up30) || 0;
      const down30 = num(revisions.down30) || 0;
      return {
        symbol,
        name: names.get(symbol) || quote.name || symbol,
        eps30,
        price30,
        gap: eps30 !== null && price30 !== null ? eps30 - price30 : null,
        analysts: num((period.earnings || {}).analysts) || 0,
        up30,
        down30,
        forwardPE: num(val.forwardPE),
        techScore: num(tr.score),
        ret20: num(tr.ret20),
        volumeRatio: num(tr.volumeRatio),
        rsi: num(tr.rsi14),
        aligned: tr.aligned === true,
        cross20: tr.cross20 === true,
        perPercentile: null,
      };
    });
  }

  async function getBandPercentile(symbol) {
    if (bandCache.has(symbol)) return bandCache.get(symbol);
    const promise = (async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 2200);
      try {
        const response = await fetch(`/api/valuation-band?ticker=${encodeURIComponent(symbol)}&years=3`, {
          cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) return null;
        const payload = await response.json();
        const value = num(payload?.per?.stats?.percentile);
        return value === null ? null : clamp(value);
      } catch (_) {
        return null;
      } finally {
        clearTimeout(timer);
      }
    })();
    bandCache.set(symbol, promise);
    return promise;
  }

  async function rankRows(rows) {
    const eligible = rows
      .filter((x) => x.eps30 !== null && x.eps30 >= 0.8 && x.price30 !== null && x.gap !== null && x.gap > 0 && x.analysts >= 2 && x.up30 >= x.down30)
      .map((x) => ({ ...x, scores: computeScore(x) }))
      .sort((a, b) => b.scores.total - a.scores.total)
      .slice(0, 8);

    await Promise.all(eligible.map(async (row) => {
      row.perPercentile = await getBandPercentile(row.symbol);
      row.scores = computeScore(row);
    }));

    return eligible.sort((a, b) => b.scores.total - a.scores.total).slice(0, 3);
  }

  function tier(row) {
    const score = row.scores.total;
    if (score >= 75 && row.scores.epsScore >= 45 && row.scores.underreaction >= 35) {
      return { cls: 'strong', label: '🔥 강한 후보' };
    }
    if (score >= 60) return { cls: 'watch', label: '👀 관찰 후보' };
    return { cls: 'check', label: '⚠️ 확인 필요' };
  }

  function valuationText(row) {
    if (row.perPercentile !== null) return `PER 3Y ${row.perPercentile.toFixed(0)}%ile`;
    return row.forwardPE !== null ? `FWD ${row.forwardPE.toFixed(1)}x` : '밸류 부족';
  }

  function trendText(row) {
    if (row.techScore !== null) return `기술 ${Math.round(row.scores.trend)}`;
    return `주가 ${pct(row.price30)}`;
  }

  function whyText(row) {
    const bits = [
      `EPS ${pct(row.eps30)}`,
      `상향 ${Math.round(row.up30)} / 하향 ${Math.round(row.down30)}`,
      `주가 ${pct(row.price30)}`,
      valuationText(row),
      trendText(row),
    ];
    return bits.join(' · ');
  }

  function cautionText(row) {
    const cautions = [];
    if (row.perPercentile !== null && row.perPercentile >= 75) cautions.push('과거 대비 밸류 부담');
    if (row.price30 !== null && row.price30 <= -8) cautions.push('주가 약세 원인 확인');
    if (row.down30 > 0) cautions.push(`하향 의견 ${Math.round(row.down30)}건 병존`);
    if (row.rsi !== null && row.rsi >= 70) cautions.push('단기 과열');
    if (row.techScore !== null && row.techScore < 50) cautions.push('기술 추세 약함');
    return cautions.length ? cautions.join(' · ') : '현재 핵심 축에서 큰 경고 신호는 제한적';
  }

  function renderCandidates(section, candidates) {
    if (!candidates.length) {
      section.innerHTML = `
        <div class="home-block-head"><div><span>① 우선검토</span><h3>실적·가격·밸류·추세를 함께 본 후보</h3></div></div>
        <div class="home-v8-empty">오늘은 5개 조건을 함께 만족하는 우선검토 후보가 없습니다.</div>`;
      return;
    }

    section.innerHTML = `
      <div class="home-block-head">
        <div><span>① 우선검토</span><h3>실적·가격·밸류·추세를 함께 본 후보</h3></div>
        <button type="button" data-priority-discover>전체 후보 →</button>
      </div>
      <div class="home-priority-method">
        <span>EPS 상향 <b>30%</b></span><i>+</i><span>상향 의견 폭 <b>15%</b></span><i>+</i><span>주가 미반영 <b>20%</b></span><i>+</i><span>밸류 <b>20%</b></span><i>+</i><span>추세 <b>15%</b></span>
        <small>우선검토 점수는 매수 점수가 아니라 오늘 먼저 확인할 순서를 정하는 탐색 지표입니다.</small>
      </div>
      <div class="home-opportunity-grid home-priority-grid">${candidates.map((row, index) => {
        const t = tier(row);
        return `
          <article class="home-opportunity-card home-priority-card">
            <div class="home-priority-top">
              <span class="home-rank">${index + 1}</span>
              <div class="home-priority-name"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)}</small></div>
              <span class="home-priority-tier ${t.cls}">${t.label}</span>
              <div class="home-priority-score"><small>우선검토</small><strong>${Math.round(row.scores.total)}</strong></div>
            </div>
            <div class="home-priority-metrics">
              <div><span>EPS 30D</span><strong class="pos">${pct(row.eps30)}</strong></div>
              <div><span>상향/하향</span><strong>${Math.round(row.up30)}↑ / ${Math.round(row.down30)}↓</strong></div>
              <div><span>미반영</span><strong class="accent">${pct(row.gap)}</strong></div>
              <div><span>밸류</span><strong>${valuationText(row)}</strong></div>
              <div><span>추세</span><strong>${trendText(row)}</strong></div>
            </div>
            <div class="home-priority-reason"><b>왜 볼까</b><span>${esc(whyText(row))}</span></div>
            <div class="home-priority-caution"><b>확인</b><span>${esc(cautionText(row))}</span></div>
            <button type="button" class="home-analyze-btn" data-priority-symbol="${esc(row.symbol)}" data-priority-name="${esc(row.name)}">이 종목 한 번에 분석 →</button>
          </article>`;
      }).join('')}</div>`;

    section.querySelectorAll('[data-priority-symbol]').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.prioritySymbol;
        const name = button.dataset.priorityName;
        if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
        if (typeof window.switchTab === 'function') window.switchTab('chart');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
    section.querySelector('[data-priority-discover]')?.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('revision');
      else if (typeof window.switchTab === 'function') window.switchTab('revision');
      if (typeof window.__loadRevisionRadar === 'function') window.__loadRevisionRadar();
    });
  }

  async function enhancePriority() {
    const section = document.querySelector('#home-v8-body .home-primary');
    if (!section || section.dataset.priorityLoading === '1') return;
    const seq = ++enhanceSeq;
    section.dataset.priorityLoading = '1';
    try {
      const [consensus, screener, valuation] = await Promise.all([
        fetch('/static/data/consensus_cache.json', { cache: 'no-store' }).then((r) => r.ok ? r.json() : { quotes: {} }),
        fetch('/static/data/screener.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : { stocks: [] }),
        fetch('/static/data/valuation_cache.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : { quotes: {} }),
      ]);
      const candidates = await rankRows(buildRows(consensus, screener, valuation));
      if (seq !== enhanceSeq || !document.body.contains(section)) return;
      renderCandidates(section, candidates);
      section.dataset.priorityV10 = '1';
    } catch (error) {
      console.warn('priority ranking unavailable:', error);
    } finally {
      section.dataset.priorityLoading = '0';
    }
  }

  function updateHero() {
    const hero = document.querySelector('.home-v8-hero');
    if (!hero) return;
    const paragraph = hero.querySelector('p');
    if (paragraph) paragraph.textContent = '실적·가격·밸류·추세를 함께 비교해 오늘 먼저 볼 종목을 정했습니다.';
  }

  function install() {
    if (window.__priorityV10Installed) return true;
    if (typeof window.__loadHomeDashboard !== 'function') return false;
    const base = window.__loadHomeDashboard;
    window.__loadHomeDashboard = async function () {
      await base();
      updateHero();
      await enhancePriority();
    };
    window.__priorityV10Installed = true;
    updateHero();
    if (document.querySelector('#home-v8-body .home-primary')) enhancePriority();

    const root = document.getElementById('home-v8-body');
    if (root) {
      const observer = new MutationObserver(() => {
        updateHero();
        const section = root.querySelector('.home-primary');
        if (section && section.dataset.priorityV10 !== '1' && section.dataset.priorityLoading !== '1') enhancePriority();
      });
      observer.observe(root, { childList: true, subtree: false });
    }
    return true;
  }

  if (!install()) {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (install() || attempts >= 40) clearInterval(timer);
    }, 150);
  }
})();
