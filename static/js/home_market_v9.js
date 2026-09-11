(() => {
  'use strict';

  const MARKET_ITEMS = [
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

  function previousFromReturn(price, ret) {
    if (price === null || ret === null || Math.abs(100 + ret) < 0.0001) return null;
    return price / (1 + ret / 100);
  }

  function formatChange(item, row) {
    const price = num(row?.price);
    const ret = num(row?.return);
    if (ret === null) return { text: '-', dir: 'flat' };

    if (item.kind === 'yield' && price !== null) {
      const prev = previousFromReturn(price, ret);
      if (prev !== null) {
        const bp = (price - prev) * 100;
        return { text: `${bp > 0 ? '+' : ''}${bp.toFixed(Math.abs(bp) < 1 ? 1 : 0)}bp`, dir: bp > 0 ? 'up' : bp < 0 ? 'down' : 'flat' };
      }
    }

    if (item.kind === 'vix' && price !== null) {
      const prev = previousFromReturn(price, ret);
      if (prev !== null) {
        const pt = price - prev;
        return { text: `${pt > 0 ? '+' : ''}${pt.toFixed(1)}pt`, dir: pt > 0 ? 'up' : pt < 0 ? 'down' : 'flat' };
      }
    }

    return { text: `${ret > 0 ? '+' : ''}${ret.toFixed(2)}%`, dir: ret > 0 ? 'up' : ret < 0 ? 'down' : 'flat' };
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
      <div class="home-market-v9-foot">60초마다 자동 갱신 · 장외/휴장 시 최근 거래값</div>`;
    home.insertBefore(panel, home.firstChild);
    panel.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('macro');
    });
    return panel;
  }

  async function loadMarket(force = false) {
    if (!isHomeActive()) return;
    const panel = ensurePanel();
    if (!panel) return;
    if (!force && Date.now() - lastLoadedAt < 45_000) return;

    const seq = ++marketLoadSeq;
    try {
      const params = new URLSearchParams({
        tickers: MARKET_ITEMS.map((x) => x.symbol).join(','),
        period: '1d',
      });
      const response = await fetch(`/api/compare?${params.toString()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`market HTTP ${response.status}`);
      const data = await response.json();
      if (seq !== marketLoadSeq) return;

      const rows = new Map((data.stocks || []).map((row) => [row.ticker, row]));
      MARKET_ITEMS.forEach((item) => {
        const node = panel.querySelector(`[data-market-symbol="${CSS.escape(item.symbol)}"]`);
        if (!node) return;
        const row = rows.get(item.symbol);
        const change = formatChange(item, row);
        node.classList.remove('is-loading');
        node.innerHTML = `
          <span>${item.label}</span>
          <strong>${formatValue(item, row)}</strong>
          <small class="${change.dir}">${change.text}</small>`;
      });

      const now = new Date();
      const time = panel.querySelector('#home-market-v9-time');
      if (time) time.textContent = `${now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })} 확인`;
      lastLoadedAt = Date.now();
    } catch (error) {
      console.warn('home market snapshot failed', error);
      const time = panel.querySelector('#home-market-v9-time');
      if (time) time.textContent = '일부 데이터 확인 필요';
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
      if (ensurePanel()) {
        clearInterval(timer);
        loadMarket(true);
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
