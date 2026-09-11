(() => {
  'use strict';

  const MARKET_ITEMS = [
    { symbol: '^KS11', label: 'KOSPI', kind: 'index' },
    { symbol: '^KQ11', label: 'KOSDAQ', kind: 'index' },
    { symbol: '^GSPC', label: 'S&P 500', kind: 'index' },
    { symbol: '^IXIC', label: 'NASDAQ', kind: 'index' },
    { symbol: '^TNX', label: '미 10년물', kind: 'yield' },
    { symbol: '^VIX', label: 'VIX', kind: 'vix' },
    { symbol: 'CL=F', label: 'WTI 유가', kind: 'oil' },
    { symbol: 'KRW=X', label: '원/달러', kind: 'fx' },
  ];

  let marketTimer = null;
  let marketLoadSeq = 0;
  let lastLoadedAt = 0;

  const num = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  function isHomeActive() {
    return Boolean(
      document.querySelector('.app-bottom-btn[data-app-mode="home"].active') ||
      document.getElementById('home-tab')?.classList.contains('active')
    );
  }

  function syncHomeChrome() {
    document.body.classList.toggle('home-clean-mode', isHomeActive());
  }

  function installHomeChromeObserver() {
    syncHomeChrome();
    const bodyObserver = new MutationObserver(syncHomeChrome);
    bodyObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    setTimeout(syncHomeChrome, 250);
    setTimeout(syncHomeChrome, 1000);
  }

  function formatValue(item, row) {
    const price = num(row?.price);
    if (price === null) return '-';
    if (item.kind === 'yield') return `${price.toFixed(2)}%`;
    if (item.kind === 'oil') return `$${price.toFixed(2)}`;
    if (item.kind === 'fx') return `₩${Math.round(price).toLocaleString('ko-KR')}`;
    if (item.kind === 'vix') return price.toFixed(1);
    return price.toLocaleString('ko-KR', { maximumFractionDigits: 1 });
  }

  function previousFromPercentChange(price, changePct) {
    if (price === null || changePct === null || Math.abs(100 + changePct) < 0.0001) return null;
    return price / (1 + changePct / 100);
  }

  function formatChange(item, row) {
    const price = num(row?.price);
    const changePct = num(row?.change);
    if (changePct === null) return { text: '-', dir: 'flat' };

    if (item.kind === 'yield' && price !== null) {
      const prev = previousFromPercentChange(price, changePct);
      if (prev !== null) {
        const bp = (price - prev) * 100;
        return { text: `${bp > 0 ? '+' : ''}${bp.toFixed(Math.abs(bp) < 1 ? 1 : 0)}bp`, dir: bp > 0 ? 'up' : bp < 0 ? 'down' : 'flat' };
      }
    }

    if (item.kind === 'vix' && price !== null) {
      const prev = previousFromPercentChange(price, changePct);
      if (prev !== null) {
        const pt = price - prev;
        return { text: `${pt > 0 ? '+' : ''}${pt.toFixed(1)}pt`, dir: pt > 0 ? 'up' : pt < 0 ? 'down' : 'flat' };
      }
    }

    return { text: `${changePct > 0 ? '+' : ''}${changePct.toFixed(2)}%`, dir: changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat' };
  }

  function ensurePanel() {
    const home = document.querySelector('#home-tab .home-v8');
    if (!home) return null;
    let panel = document.getElementById('home-market-v9');
    if (panel) return panel;

    panel = document.createElement('section');
    panel.id = 'home-market-v9';
    panel.className = 'home-market-v9';
    panel.innerHTML = `
      <div class="home-market-v9-head">
        <div>
          <span class="home-market-v9-kicker">MARKET NOW</span>
          <strong>오늘의 시장</strong>
        </div>
        <span id="home-market-v9-time">불러오는 중...</span>
      </div>
      <div id="home-market-v9-grid" class="home-market-v9-grid">
        ${MARKET_ITEMS.map((item) => `
          <div class="home-market-v9-item is-loading" data-market-symbol="${item.symbol}">
            <span>${item.label}</span><strong>-</strong><small>확인 중</small>
          </div>`).join('')}
      </div>
      <div class="home-market-v9-foot">등락은 직전 종가 대비 · 60초마다 갱신 · 휴장/장외에는 최근 거래값</div>`;
    const anchor = document.getElementById('home-v8-body');
    if (anchor && anchor.parentElement === home) home.insertBefore(panel, anchor);
    else home.prepend(panel);
    return panel;
  }

  function formatCheckedAt(data) {
    const raw = String(data?.timestamp || '').trim();
    if (raw) {
      const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})/);
      if (match) return `${match[2]}.${match[3]} ${match[4]} KST`;
    }
    const now = new Date();
    return `${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')} ${now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })}`;
  }

  function paintMarket(panel, data) {
    if (!panel || !data) return false;
    const rows = new Map((data.results || []).map((row) => [row.ticker, row]));
    let painted = 0;
    MARKET_ITEMS.forEach((item) => {
      const node = panel.querySelector(`[data-market-symbol="${CSS.escape(item.symbol)}"]`);
      if (!node) return;
      const row = rows.get(item.symbol);
      if (!row) return;
      const change = formatChange(item, row);
      node.classList.remove('is-loading');
      node.innerHTML = `
        <span>${item.label}</span>
        <strong>${formatValue(item, row)}</strong>
        <small class="${change.dir}">${change.text}</small>`;
      painted += 1;
    });
    const time = panel.querySelector('#home-market-v9-time');
    if (time && painted) time.textContent = `${formatCheckedAt(data)} 기준`;
    return painted > 0;
  }

  function saveMarketLocal(data) {
    try { localStorage.setItem('chartview-market-now-v21', JSON.stringify(data)); } catch (_) {}
  }

  function readMarketLocal() {
    try {
      const raw = localStorage.getItem('chartview-market-now-v21');
      return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
  }

  async function loadMarket(force = false) {
    if (!isHomeActive()) return;
    const panel = ensurePanel();
    if (!panel) return;
    if (!force && Date.now() - lastLoadedAt < 45_000) return;

    const seq = ++marketLoadSeq;
    try {
      const response = await fetch(`/api/market-now${force ? '?fresh=1' : ''}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`market HTTP ${response.status}`);
      const data = await response.json();
      if (seq !== marketLoadSeq) return;
      if (paintMarket(panel, data)) {
        saveMarketLocal(data);
        lastLoadedAt = Date.now();
      }
    } catch (error) {
      console.warn('home market snapshot failed', error);
      const time = panel.querySelector('#home-market-v9-time');
      if (time && !readMarketLocal()) time.textContent = '일부 데이터 확인 필요';
    }
  }

  function startRefreshLoop() {
    if (marketTimer) clearInterval(marketTimer);
    marketTimer = setInterval(() => {
      syncHomeChrome();
      if (isHomeActive() && document.visibilityState === 'visible') loadMarket(true);
    }, 60_000);
  }

  function init() {
    installHomeChromeObserver();
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      syncHomeChrome();
      const panel = ensurePanel();
      if (panel) {
        clearInterval(timer);
        const local = readMarketLocal();
        if (local) paintMarket(panel, local);
        loadMarket(false);
        setTimeout(() => loadMarket(true), 450);
        startRefreshLoop();
      } else if (attempts >= 40) {
        clearInterval(timer);
      }
    }, 150);

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && isHomeActive()) loadMarket(true);
    });
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn')) {
        requestAnimationFrame(() => {
          syncHomeChrome();
          if (isHomeActive()) {
            ensurePanel();
            loadMarket();
          }
        });
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();