(() => {
  'use strict';

  let homePromise = null;
  let screenerPromise = null;
  let activeBriefTicker = null;
  let briefSeq = 0;
  const briefCache = new Map();

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const n = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const x = Number(value);
    return Number.isFinite(x) ? x : null;
  };
  const pct = (value, digits = 1) => {
    const x = n(value);
    return x === null ? '-' : `${x > 0 ? '+' : ''}${x.toFixed(digits)}%`;
  };
  const mult = (value, digits = 1) => {
    const x = n(value);
    return x === null ? '-' : `${x.toFixed(digits)}x`;
  };
  const revisionPct = (current, previous) => {
    const a = n(current), b = n(previous);
    if (a === null || b === null || a <= 0 || b <= 0) return null;
    return (a / b - 1) * 100;
  };

  const HOME_MAJOR_STOCKS = [
    { symbol: '005930.KS', name: '삼성전자', logo: '/static/logos/samsung.svg', fallback: '삼성', logoClass: 'wide' },
    { symbol: '000660.KS', name: 'SK하이닉스', logo: '/static/logos/skhynix.svg', fallback: 'SK', logoClass: 'wide' },
    { symbol: 'NVDA', name: '엔비디아', logo: '/static/logos/nvidia.svg', fallback: 'NV' },
    { symbol: 'AAPL', name: '애플', logo: '/static/logos/apple.svg', fallback: 'A', logoClass: 'tall' },
    { symbol: 'MSFT', name: '마이크로소프트', logo: '/static/logos/microsoft.svg', fallback: 'MS', logoClass: 'square' },
    { symbol: 'META', name: '메타', logo: '/static/logos/meta.svg', fallback: 'M' },
    { symbol: 'TSLA', name: '테슬라', logo: '/static/logos/tesla.svg', fallback: 'T', logoClass: 'tall' },
    { symbol: 'GOOGL', name: '알파벳', logo: '/static/logos/google.svg', fallback: 'G', logoClass: 'square' },
  ];

  function homeLogo(item) {
    const label = esc(item.fallback || String(item.name || item.symbol || '?').slice(0, 2));
    const fallback = `<span class="home16-logo-fallback">${label}</span>`;
    if (!item.logo) return `<span class="home16-logo">${fallback}</span>`;
    const logoClass = item.logoClass ? ` logo-${esc(item.logoClass)}` : '';
    return `<span class="home16-logo"><img class="${logoClass.trim()}" src="${esc(item.logo)}" alt="${esc(item.name)} 로고" loading="eager" decoding="async" onerror="this.remove()">${fallback}</span>`;
  }

  function homePrice(symbol, value) {
    const price = n(value);
    if (price === null) return '-';
    if (/\.(KS|KQ)$/.test(symbol)) return `₩${Math.round(price).toLocaleString('ko-KR')}`;
    return `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function homeChangeClass(value) {
    const x = n(value) || 0;
    return x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
  }

  function homeCheckedAt(raw) {
    const match = String(raw || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (match) return `${match[2]}.${match[3]} ${match[4]}:${match[5]}`;
    try {
      return new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
        .format(new Date()).replace(/\. /g, '.').replace(/\.$/, '');
    } catch (_) { return '최신'; }
  }

  function majorRows(heatmap) {
    const map = new Map((heatmap?.results || []).map((row) => [row.ticker, row]));
    return HOME_MAJOR_STOCKS.map((item) => ({ ...(map.get(item.symbol) || {}), ...item }));
  }

  function majorStocksHtml(rows, generatedAt) {
    return `
      <section class="home-v8-block home16-major-card">
        <div class="home-block-head home16-head">
          <div><span>MARKET</span><h3>주요 종목 오늘 시황</h3></div>
          <small>${esc(homeCheckedAt(generatedAt))} 기준</small>
        </div>
        <div class="home16-stock-strip">${rows.map((row) => `
          <button type="button" class="home16-stock" data-home-symbol="${esc(row.symbol)}" data-home-name="${esc(row.name)}">
            <span class="home16-ring">${homeLogo(row)}</span>
            <strong>${esc(row.name)}</strong>
            <small>${homePrice(row.symbol, row.price)}</small>
            <b class="${homeChangeClass(row.change)}">${pct(row.change, 2)}</b>
          </button>`).join('')}</div>
        <div class="home16-caption">직전 종가 대비 · 캐시 즉시 표시 후 최신 시세로 자동 갱신</div>
      </section>`;
  }

  function moversHtml(rows) {
    const available = rows.filter((row) => n(row.change) !== null);
    const movers = [...available].sort((a, b) => Math.abs(n(b.change)) - Math.abs(n(a.change))).slice(0, 4);
    if (!movers.length) return '';
    return `
      <section class="home-v8-block home16-movers-card">
        <div class="home-block-head home16-head"><div><span>TODAY</span><h3>오늘 많이 움직인 종목</h3></div></div>
        <div class="home16-movers">${movers.map((row, index) => `
          <button type="button" class="home16-mover" data-home-symbol="${esc(row.symbol)}" data-home-name="${esc(row.name)}">
            <span class="home16-mover-rank">${index + 1}</span>
            ${homeLogo(row)}
            <span class="home16-mover-copy"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)} · ${homePrice(row.symbol, row.price)}</small></span>
            <b class="${homeChangeClass(row.change)}">${pct(row.change, 2)}</b><i>›</i>
          </button>`).join('')}</div>
      </section>`;
  }

  function marketSummaryHtml(macro) {
    const summary = typeof macro?.summary === 'string' ? macro.summary : macro?.summary?.text;
    const rawLevel = typeof macro?.summary === 'object' ? macro?.summary?.level : null;
    const level = ['green', 'yellow', 'red'].includes(rawLevel) ? rawLevel : 'yellow';
    const state = level === 'green'
      ? { label: '시장 우호적', desc: '위험 지표가 비교적 안정적입니다.' }
      : level === 'red'
        ? { label: '리스크 경계', desc: '방어적으로 확인할 구간입니다.' }
        : { label: '중립 · 주의', desc: '지표가 엇갈려 선별 접근이 필요합니다.' };
    const stale = Number(macro?.staleCount || 0);
    return `
      <section class="home-v8-block home16-summary-card home18-summary-${level}">
        <div class="home-block-head home16-head"><div><span>SUMMARY</span><h3>시장 한줄 요약</h3></div><button type="button" data-home-market>시장 자세히 →</button></div>
        <div class="home18-state-card">
          <div class="home18-traffic" aria-label="현재 시장 신호 ${esc(state.label)}">
            <i class="red ${level === 'red' ? 'active' : ''}"></i>
            <i class="yellow ${level === 'yellow' ? 'active' : ''}"></i>
            <i class="green ${level === 'green' ? 'active' : ''}"></i>
          </div>
          <div class="home18-state-copy"><span>현재 시장 상태</span><strong>${esc(state.label)}</strong><small>${esc(state.desc)}</small></div>
        </div>
        <p>${esc(summary || '주요 지수와 종목별 움직임을 확인해 주세요.')}</p>
        <div class="home16-summary-foot"><span class="${stale ? 'warn' : 'ok'}"></span>${stale ? `일부 매크로 지표 ${stale}개 갱신 지연` : '매크로 데이터 정상 갱신'}</div>
      </section>`;
  }

  function selectedTickersNow() {
    try {
      if (typeof selectedTickers !== 'undefined' && Array.isArray(selectedTickers)) return [...selectedTickers];
    } catch (_) {}
    try {
      if (typeof perTickers !== 'undefined' && Array.isArray(perTickers)) return [...perTickers];
    } catch (_) {}
    return [];
  }

  function displayName(symbol) {
    try { if (typeof tickerNameMap !== 'undefined' && tickerNameMap[symbol]) return tickerNameMap[symbol]; } catch (_) {}
    try { if (typeof perTickerNameMap !== 'undefined' && perTickerNameMap[symbol]) return perTickerNameMap[symbol]; } catch (_) {}
    return symbol;
  }

  function installHome() {
    if (document.getElementById('home-tab')) return;
    const chartTab = document.getElementById('chart-tab');
    if (!chartTab) return;
    const tab = document.createElement('div');
    tab.id = 'home-tab';
    tab.className = 'tab-content home-tab';
    tab.innerHTML = `
      <section class="home-v8 home16-market-home">
        <div id="home-v8-body"><div class="home-v8-loading"><div class="spinner"></div><span>오늘 시황을 불러오는 중...</span></div></div>
      </section>`;
    chartTab.insertAdjacentElement('beforebegin', tab);
  }

  function installBrief() {
    if (document.getElementById('stock-brief-v8')) return;
    const chartTab = document.getElementById('chart-tab');
    const anchor = chartTab?.querySelector('.chart-section');
    if (!chartTab || !anchor) return;
    const section = document.createElement('section');
    section.id = 'stock-brief-v8';
    section.className = 'stock-brief-v8';
    section.innerHTML = `
      <div class="stock-brief-head">
        <div><span class="stock-brief-kicker">한눈에 판단</span><h2>선택 종목 요약</h2><p>수익률 흐름을 먼저 확인한 뒤 밸류·실적 상태를 이어서 봅니다.</p></div>
      </div>
      <div id="stock-brief-tabs" class="stock-brief-tabs"></div>
      <div id="stock-brief-body" class="stock-brief-body"><div class="stock-brief-empty">상단에서 종목을 선택해 주세요.</div></div>`;
    anchor.insertAdjacentElement('afterend', section);
    renderBriefTabs();
  }

  function loadScreener() {
    if (!screenerPromise) {
      screenerPromise = fetch('/static/data/screener.json', { cache: 'force-cache' })
        .then((r) => r.ok ? r.json() : { stocks: [] })
        .catch(() => ({ stocks: [] }));
    }
    return screenerPromise;
  }

  function loadHomeSources(fresh = false) {
    const request = () => fetch(`/api/home-snapshot${fresh ? '?fresh=1' : ''}`, { cache: 'no-store' })
      .then((r) => { if (!r.ok) throw new Error(`home snapshot HTTP ${r.status}`); return r.json(); });
    if (fresh) return request();
    if (!homePromise) homePromise = request();
    return homePromise;
  }

  function saveHomeLocal(snapshot) {
    try { localStorage.setItem('chartview-home-snapshot-v17', JSON.stringify(snapshot)); } catch (_) {}
  }

  function readHomeLocal() {
    try {
      const raw = localStorage.getItem('chartview-home-snapshot-v17');
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }

  function paintHome(root, snapshot) {
    const rows = majorRows(snapshot?.heatmap || { results: [] });
    root.innerHTML = majorStocksHtml(rows, snapshot?.generatedAt) + marketSummaryHtml(snapshot?.macro);
    bindHomeActions(root);
  }

  function buildOpportunityRows(consensus, screener, valuation) {
    const names = new Map((screener.stocks || []).map((x) => [x.symbol, x.name]));
    const tech = new Map((screener.stocks || []).map((x) => [x.symbol, x]));
    const vq = valuation.quotes || {};
    return Object.entries(consensus.quotes || {}).map(([symbol, quote]) => {
      const row = (quote.periods || {})['0y'] || {};
      const trend = row.epsTrend || {};
      const revisions = row.revisions || {};
      const eps30 = revisionPct(trend.current ?? (row.earnings || {}).avg, trend['30daysAgo']);
      const price30 = n((quote.priceTrend || {}).return30);
      const analysts = n((row.earnings || {}).analysts) || 0;
      const balance = (n(revisions.up30) || 0) - (n(revisions.down30) || 0);
      const gap = eps30 !== null && price30 !== null ? eps30 - price30 : null;
      const val = vq[symbol] || {};
      const tr = tech.get(symbol) || {};
      return {
        symbol,
        name: names.get(symbol) || quote.name || symbol,
        eps30, price30, gap, analysts, balance,
        forwardPE: n(val.forwardPE), roe: n(val.roe),
        techScore: n(tr.score), ret20: n(tr.ret20), volumeRatio: n(tr.volumeRatio), rsi: n(tr.rsi14),
      };
    });
  }

  function opportunityCards(rows) {
    const candidates = rows
      .filter((x) => x.eps30 !== null && x.eps30 >= 1 && x.price30 !== null && x.gap !== null && x.gap >= 2 && x.analysts >= 2 && x.balance >= 0)
      .sort((a, b) => (b.gap - a.gap) || (b.eps30 - a.eps30))
      .slice(0, 3);
    if (!candidates.length) return '<div class="home-v8-empty">오늘 조건에 맞는 실적-주가 괴리 후보가 없습니다.</div>';
    return `<div class="home-opportunity-grid">${candidates.map((x, i) => `
      <article class="home-opportunity-card">
        <div class="home-opportunity-top"><span class="home-rank">${i + 1}</span><div><strong>${esc(x.name)}</strong><small>${esc(x.symbol)}</small></div><span class="home-signal">실적↑ · 주가 미반영</span></div>
        <div class="home-opportunity-metrics">
          <div><span>EPS 30D</span><strong class="pos">${pct(x.eps30)}</strong></div>
          <div><span>주가 30D</span><strong>${pct(x.price30)}</strong></div>
          <div><span>괴리</span><strong class="accent">${pct(x.gap)}</strong></div>
          <div><span>FWD PER</span><strong>${mult(x.forwardPE)}</strong></div>
        </div>
        <button type="button" class="home-analyze-btn" data-home-symbol="${esc(x.symbol)}" data-home-name="${esc(x.name)}">이 종목 한 번에 분석 →</button>
      </article>`).join('')}</div>`;
  }

  function technicalCards(screener) {
    const rows = (screener.stocks || [])
      .filter((x) => n(x.score) !== null && n(x.score) >= 55 && n(x.volumeRatio) !== null && n(x.volumeRatio) >= 1.2 && (n(x.rsi14) === null || n(x.rsi14) < 70))
      .sort((a, b) => (n(b.score) - n(a.score)) || (n(b.volumeRatio) - n(a.volumeRatio)))
      .slice(0, 3);
    if (!rows.length) return '<div class="home-v8-empty">현재 기술 조건에 맞는 후보가 없습니다.</div>';
    return `<div class="home-tech-list">${rows.map((x) => `
      <button type="button" class="home-tech-row" data-home-symbol="${esc(x.symbol)}" data-home-name="${esc(x.name)}">
        <span class="home-tech-name"><strong>${esc(x.name)}</strong><small>${esc(x.market || '')} · ${esc(x.code || '')}</small></span>
        <span><small>기술점수</small><strong>${Math.round(n(x.score) || 0)}</strong></span>
        <span><small>거래량</small><strong>${n(x.volumeRatio) === null ? '-' : `${n(x.volumeRatio).toFixed(1)}x`}</strong></span>
        <span><small>20일</small><strong class="${(n(x.ret20) || 0) >= 0 ? 'pos' : 'neg'}">${pct(x.ret20)}</strong></span>
        <i>›</i>
      </button>`).join('')}</div>`;
  }

  function macroBlock(macro) {
    if (!macro) return '<div class="home-v8-empty">시장 환경 데이터를 불러오지 못했습니다.</div>';
    const summary = typeof macro.summary === 'string' ? { text: macro.summary, level: 'yellow' } : (macro.summary || {});
    const map = new Map((macro.results || []).map((x) => [x.original_symbol || x.symbol, x]));
    const vix = map.get('^VIX');
    const curve = map.get('T10Y2Y');
    const hy = map.get('BAMLH0A0HYM2');
    const level = summary.level || 'yellow';
    const label = level === 'green' ? '안정' : level === 'red' ? '위험' : '주의';
    return `
      <div class="home-market-card ${level}">
        <div class="home-market-head"><div><span class="home-market-light"></span><strong>시장 환경 · ${label}</strong></div><button type="button" data-home-market>시장 자세히 →</button></div>
        <p>${esc(summary.text || '시장 요약을 확인해 주세요.')}</p>
        <div class="home-market-metrics">
          <div><span>VIX</span><strong>${vix ? Number(vix.value).toFixed(1) : '-'}</strong></div>
          <div><span>10Y-2Y</span><strong>${curve ? `${Number(curve.value).toFixed(2)}%` : '-'}</strong></div>
          <div><span>HY Spread</span><strong>${hy ? `${Number(hy.value).toFixed(2)}%` : '-'}</strong></div>
          <div><span>데이터</span><strong>${Number(macro.staleCount || 0) ? '일부 지연' : '정상'}</strong></div>
        </div>
      </div>`;
  }

  async function renderHome() {
    const root = document.getElementById('home-v8-body');
    if (!root) return;

    // 1) Same-device cache paints synchronously, so returning users never stare at a spinner.
    const local = readHomeLocal();
    if (local?.heatmap?.results?.length) paintHome(root, local);
    else if (!root.querySelector('.home16-major-card')) {
      root.innerHTML = '<div class="home-v8-loading"><div class="spinner"></div><span>마지막 시황을 불러오는 중...</span></div>';
    }

    try {
      // 2) Shared server cache is returned immediately for every visitor.
      homePromise = null;
      const cached = await loadHomeSources(false);
      if (cached?.heatmap?.results?.length) {
        paintHome(root, cached);
        saveHomeLocal(cached);
      }

      // 3) Latest quotes refresh behind the already-painted UI. Never block Home on this request.
      loadHomeSources(true).then((fresh) => {
        if (!fresh?.heatmap?.results?.length) return;
        saveHomeLocal(fresh);
        if (document.body.contains(root)) paintHome(root, fresh);
      }).catch((error) => console.warn('home background refresh failed', error));
    } catch (error) {
      console.error('home market dashboard failed', error);
      if (!root.querySelector('.home16-major-card')) {
        root.innerHTML = '<div class="home-v8-empty">마지막 시황을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
      }
    }
  }

  function openAnalysis(symbol, name) {
    if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
    activeBriefTicker = symbol;
    if (typeof window.switchTab === 'function') window.switchTab('chart');
    renderBriefTabs();
    loadBrief(symbol);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function bindHomeActions(root) {
    root.querySelectorAll('[data-home-symbol]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.homeSymbol, button.dataset.homeName)));
    root.querySelector('[data-home-discover]')?.addEventListener('click', () => {
      if (typeof window.switchTab === 'function') window.switchTab('revision');
      if (typeof window.__loadRevisionRadar === 'function') window.__loadRevisionRadar();
    });
    root.querySelector('[data-home-screener]')?.addEventListener('click', () => {
      const b = document.querySelector('.tab-nav [data-tab="screener"]'); if (b) b.click(); else if (typeof window.switchTab === 'function') window.switchTab('screener');
    });
    root.querySelector('[data-home-market]')?.addEventListener('click', () => { if (typeof window.switchTab === 'function') window.switchTab('macro'); });
  }

  function renderBriefTabs() {
    const tabs = document.getElementById('stock-brief-tabs');
    const body = document.getElementById('stock-brief-body');
    if (!tabs || !body) return;
    const list = selectedTickersNow();
    if (!list.length) {
      tabs.innerHTML = '';
      body.innerHTML = '<div class="stock-brief-empty">상단에서 종목을 선택하면 한눈에 요약이 표시됩니다.</div>';
      activeBriefTicker = null;
      return;
    }
    if (!activeBriefTicker || !list.includes(activeBriefTicker)) activeBriefTicker = list[0];
    tabs.innerHTML = list.map((symbol) => `<button type="button" class="stock-brief-tab ${symbol === activeBriefTicker ? 'active' : ''}" data-brief-ticker="${esc(symbol)}">${esc(displayName(symbol))}</button>`).join('');
    tabs.querySelectorAll('[data-brief-ticker]').forEach((button) => button.addEventListener('click', () => {
      activeBriefTicker = button.dataset.briefTicker;
      renderBriefTabs();
      loadBrief(activeBriefTicker);
    }));
    loadBrief(activeBriefTicker);
  }

  async function fetchBrief(symbol) {
    if (briefCache.has(symbol)) return briefCache.get(symbol);
    const promise = (async () => {
      const screener = await loadScreener();
      const local = (screener.stocks || []).find((x) => x.symbol === symbol) || null;
      const [valuationRes, consensusRes, bandRes] = await Promise.allSettled([
        fetch(`/api/valuation?tickers=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
        fetch(`/api/consensus?ticker=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
        fetch(`/api/valuation-band?ticker=${encodeURIComponent(symbol)}&years=3`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
      ]);
      const valuationPayload = valuationRes.status === 'fulfilled' ? valuationRes.value : null;
      return {
        valuation: valuationPayload?.stocks?.[0] || null,
        consensus: consensusRes.status === 'fulfilled' ? consensusRes.value : null,
        band: bandRes.status === 'fulfilled' ? bandRes.value : null,
        local,
      };
    })();
    briefCache.set(symbol, promise);
    return promise;
  }

  function statusPills(data) {
    const v = data.valuation || {};
    const c = data.consensus || {};
    const y = (c.periods || {})['0y'] || {};
    const t = y.epsTrend || {};
    const eps30 = revisionPct(t.current ?? (y.earnings || {}).avg, t['30daysAgo']);
    const p30 = n((c.priceTrend || {}).return30) ?? n(data.local?.ret20);
    const perPct = n(data.band?.per?.stats?.percentile);
    const valuation = perPct === null ? '밸류 확인 필요' : perPct <= 30 ? '과거 대비 낮은 밸류' : perPct >= 80 ? '과거 대비 높은 밸류' : '밸류 중립';
    const earnings = eps30 === null ? '실적 추정치 없음' : eps30 >= 2 ? '실적 추정치 ↑' : eps30 <= -2 ? '실적 추정치 ↓' : '실적 추정치 보합';
    const momentum = p30 === null ? '주가 추세 확인 필요' : p30 >= 5 ? '주가 추세 ↑' : p30 <= -5 ? '주가 추세 ↓' : '주가 추세 중립';
    return { valuation, earnings, momentum, eps30, p30, perPct, forwardPE: n(v.forwardPE), pbr: n(v.pbr), roe: n(v.roe) };
  }

  function insightText(s) {
    const positive = [];
    const caution = [];
    if (s.eps30 !== null && s.eps30 >= 2) positive.push(`EPS 컨센서스 30일 ${pct(s.eps30)} 상향`);
    if (s.perPct !== null && s.perPct <= 30) positive.push(`PER이 3년 하위 ${s.perPct.toFixed(0)}% 구간`);
    if (s.p30 !== null && s.p30 >= 5) positive.push(`최근 주가 흐름 ${pct(s.p30)}`);
    if (s.eps30 !== null && s.eps30 <= -2) caution.push(`EPS 컨센서스 ${pct(s.eps30)} 하향`);
    if (s.perPct !== null && s.perPct >= 80) caution.push(`PER이 3년 상위 ${s.perPct.toFixed(0)}% 구간`);
    if (s.p30 !== null && s.p30 <= -5) caution.push(`최근 주가 흐름 ${pct(s.p30)}`);
    return {
      positive: positive.length ? positive.join(' · ') : '뚜렷한 우호 신호는 아직 없습니다.',
      caution: caution.length ? caution.join(' · ') : '현재 핵심 지표에서 강한 경고 신호는 제한적입니다.',
    };
  }

  function renderBrief(symbol, data) {
    const body = document.getElementById('stock-brief-body');
    if (!body || symbol !== activeBriefTicker) return;
    const v = data.valuation || {};
    const s = statusPills(data);
    const insight = insightText(s);
    const price = n(v.price);
    const isKR = /\.(KS|KQ)$/.test(symbol);
    const priceText = price === null ? '-' : isKR ? `₩${Math.round(price).toLocaleString('ko-KR')}` : `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    body.innerHTML = `
      <div class="stock-brief-summary">
        <div class="stock-brief-identity"><div><strong>${esc(displayName(symbol))}</strong><span>${esc(symbol)}</span></div><b>${priceText}</b></div>
        <div class="stock-status-row"><span>${esc(s.earnings)}</span><span>${esc(s.valuation)}</span><span>${esc(s.momentum)}</span></div>
      </div>
      <div class="stock-brief-metrics">
        <div><span>FWD PER</span><strong>${mult(s.forwardPE)}</strong><small>향후 이익 기준</small></div>
        <div><span>3Y PER 위치</span><strong>${s.perPct === null ? '-' : `${s.perPct.toFixed(0)}%`}</strong><small>낮을수록 과거 대비 낮음</small></div>
        <div><span>EPS 30D</span><strong class="${(s.eps30 || 0) >= 0 ? 'pos' : 'neg'}">${pct(s.eps30)}</strong><small>애널리스트 추정치 변화</small></div>
        <div><span>주가 흐름</span><strong class="${(s.p30 || 0) >= 0 ? 'pos' : 'neg'}">${pct(s.p30)}</strong><small>30일 또는 가용 추세</small></div>
        <div><span>PBR</span><strong>${mult(s.pbr)}</strong><small>순자산 대비 가격</small></div>
        <div><span>ROE</span><strong>${s.roe === null ? '-' : `${s.roe.toFixed(1)}%`}</strong><small>자기자본 수익성</small></div>
      </div>
      <div class="stock-brief-insight"><div class="good"><span>좋게 볼 점</span><p>${esc(insight.positive)}</p></div><div class="watch"><span>확인할 점</span><p>${esc(insight.caution)}</p></div></div>
      <div class="stock-brief-actions"><button type="button" data-brief-action="fwdper">밸류 자세히</button><button type="button" data-brief-action="ideas">투자판단 보기</button></div>`;
    body.querySelectorAll('[data-brief-action]').forEach((button) => button.addEventListener('click', () => {
      const target = button.dataset.briefAction;
      const appButton = document.querySelector(`[data-app-tab="${target}"]`);
      if (appButton) appButton.click(); else if (typeof window.switchTab === 'function') window.switchTab(target);
    }));
  }

  async function loadBrief(symbol) {
    if (!symbol) return;
    const seq = ++briefSeq;
    const body = document.getElementById('stock-brief-body');
    if (body && symbol === activeBriefTicker) body.innerHTML = '<div class="stock-brief-loading"><div class="spinner"></div><span>종목의 핵심 정보를 모으는 중...</span></div>';
    try {
      const data = await fetchBrief(symbol);
      if (seq !== briefSeq) return;
      renderBrief(symbol, data);
    } catch (error) {
      console.error('stock brief failed', error);
      if (body && symbol === activeBriefTicker) body.innerHTML = '<div class="stock-brief-empty">종목 요약 일부를 불러오지 못했습니다. 상세 탭은 계속 사용할 수 있습니다.</div>';
    }
  }

  function observeSelection() {
    const tags = document.getElementById('ticker-tags');
    if (!tags) return;
    let timer = null;
    new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(renderBriefTabs, 100);
    }).observe(tags, { childList: true, subtree: true });
  }

  function init() {
    installHome();
    installBrief();
    observeSelection();
    renderBriefTabs();
  }

  window.__loadHomeDashboard = renderHome;
  window.__refreshStockBrief = renderBriefTabs;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
