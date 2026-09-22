(() => {
  'use strict';

  const HOME_SNAPSHOT_KEY = 'chartview-home-snapshot-v17';
  const HEATMAP_CACHE_KEY = 'chartview-home-heatmap-v65';
  const QUOTE_CACHE_KEY = 'chartview-watchlist-quotes-v33';
  const VIEW_KEY = 'chartview-home-major-view-v57';
  const REFRESH_MS = 300_000;
  const LIVE_QUOTE_POLL_MS = 5_000;
  const FAST_RETRY_MS = 5_000;
  const MIN_FULL_ROWS = 14;
  const LOGO_AREA_THRESHOLD = 0.12;
  const LOGO_MIN_WIDTH = 0.26;
  const LOGO_MIN_HEIGHT = 0.22;

  const STOCKS = {
    '005930.KS': { name: '삼성전자', market: 'KR', logo: '/static/logos/samsung.svg', fallback: '삼성' },
    '000660.KS': { name: 'SK하이닉스', market: 'KR', logo: '/static/logos/skhynix.svg', fallback: 'SK' },
    '207940.KS': { name: '삼성바이오로직스', market: 'KR', fallback: '삼바' },
    '005380.KS': { name: '현대차', market: 'KR', fallback: '현대' },
    '000270.KS': { name: '기아', market: 'KR', fallback: '기아' },
    '373220.KS': { name: 'LG에너지솔루션', market: 'KR', fallback: 'LG' },
    '035420.KS': { name: 'NAVER', market: 'KR', fallback: 'N' },
    '068270.KS': { name: '셀트리온', market: 'KR', fallback: '셀트' },
    'NVDA': { name: '엔비디아', market: 'US', logo: '/static/logos/nvidia.svg', fallback: 'NV' },
    'AAPL': { name: '애플', market: 'US', logo: '/static/logos/apple.svg', fallback: 'A' },
    'MSFT': { name: '마이크로소프트', market: 'US', logo: '/static/logos/microsoft.svg', fallback: 'MS' },
    'GOOGL': { name: '알파벳', market: 'US', logo: '/static/logos/google.svg', fallback: 'G' },
    'AMZN': { name: '아마존', market: 'US', fallback: 'AM' },
    'TSM': { name: 'TSMC', market: 'US', fallback: 'TSM' },
    'META': { name: '메타', market: 'US', logo: '/static/logos/meta.svg', fallback: 'M' },
    'AVGO': { name: '브로드컴', market: 'US', fallback: 'AV' },
    'TSLA': { name: '테슬라', market: 'US', logo: '/static/logos/tesla.svg', fallback: 'T' },
    'AMD': { name: 'AMD', market: 'US', fallback: 'AMD' }
  };

  let refreshTimer = null;
  let refreshKickTimer = null;
  let retryTimer = null;
  let inFlight = null;
  let quoteInFlight = null;
  let lastQuotePollAt = 0;
  let lastSignature = '';

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function isHomeActive() {
    return Boolean(
      document.querySelector('.app-bottom-btn[data-app-mode="home"].active') ||
      document.getElementById('home-tab')?.classList.contains('active')
    );
  }

  function number(value) {
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
  }

  function signedPercent(value) {
    const n = number(value);
    if (n === null) return '-';
    return (n > 0 ? '+' : '') + n.toFixed(2) + '%';
  }

  function formatPrice(symbol, value) {
    const n = number(value);
    if (n === null) return '-';
    if (/\.(KS|KQ)$/.test(symbol)) return '₩' + Math.round(n).toLocaleString('ko-KR');
    return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }

  function toneClass(value) {
    const n = number(value) || 0;
    const mag = Math.abs(n);
    const level = mag >= 3 ? 3 : mag >= 1 ? 2 : mag >= 0.25 ? 1 : 0;
    if (!level) return 'cvhm-flat';
    return (n > 0 ? 'cvhm-up-' : 'cvhm-down-') + level;
  }

  function relativeWeight(row) {
    const cap = Math.max(1, number(row.marketCap) || 1);
    // U.S.: preserve Finviz-style true market-cap area.
    // Korea: restore the stronger readability compression used by the first accepted layout so the remaining large caps
    // stay readable on mobile. The non-linear scale is explicitly labeled.
    return row.market === 'KR' ? Math.pow(cap, 0.58) : cap;
  }

  function layout(items, x, y, width, height, out) {
    if (!items.length) return;
    if (items.length === 1) {
      out.push({ row: items[0], x, y, width, height });
      return;
    }

    const total = items.reduce((sum, item) => sum + item.weight, 0);
    let partial = 0;
    let split = 1;
    let best = Infinity;
    for (let i = 1; i < items.length; i += 1) {
      partial += items[i - 1].weight;
      const diff = Math.abs(total / 2 - partial);
      if (diff < best) {
        best = diff;
        split = i;
      }
    }

    const first = items.slice(0, split);
    const second = items.slice(split);
    const firstWeight = first.reduce((sum, item) => sum + item.weight, 0);
    const ratio = total > 0 ? firstWeight / total : 0.5;

    if (width >= height) {
      const firstWidth = width * ratio;
      layout(first, x, y, firstWidth, height, out);
      layout(second, x + firstWidth, y, width - firstWidth, height, out);
    } else {
      const firstHeight = height * ratio;
      layout(first, x, y, width, firstHeight, out);
      layout(second, x, y + firstHeight, width, height - firstHeight, out);
    }
  }

  function mergedRows(payload) {
    const live = readJson(QUOTE_CACHE_KEY, { quotes: {} });
    const liveQuotes = live?.quotes || {};
    return (payload?.results || [])
      .map((raw) => {
        const symbol = String(raw?.ticker || '').toUpperCase();
        const meta = STOCKS[symbol];
        if (!meta) return null;
        const quote = liveQuotes[symbol] || {};
        return {
          symbol,
          name: meta.name,
          market: meta.market,
          logo: meta.logo || '',
          fallback: meta.fallback || symbol.slice(0, 3),
          marketCap: number(raw.marketCap) || 0,
          price: number(quote.price) ?? number(raw.price),
          change: number(quote.dayChange) ?? number(raw.change),
          asOf: quote.quoteAsOf || raw.asOf || ''
        };
      })
      .filter(Boolean);
  }

  function payloadTime(payload) {
    const parsed = Date.parse(payload?.generatedAt || '');
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function cachedPayload() {
    const own = readJson(HEATMAP_CACHE_KEY, null);
    const home = readJson(HOME_SNAPSHOT_KEY, null);
    const shared = home?.heatmap?.results?.length
      ? { results: home.heatmap.results, generatedAt: home.generatedAt || '' }
      : null;

    if (shared?.results?.length && own?.results?.length) {
      // Cards and heatmap must converge on the freshest shared Home snapshot.
      // Equal timestamps prefer Home so a newly painted card cannot be followed by stale heatmap geometry.
      return payloadTime(shared) >= payloadTime(own) ? shared : own;
    }
    return shared?.results?.length ? shared : (own?.results?.length ? own : null);
  }

  function makeLogo(row) {
    const wrap = document.createElement('span');
    wrap.className = 'cvhm-logo';

    if (row.logo) {
      const img = document.createElement('img');
      img.src = row.logo;
      img.alt = '';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.onerror = () => {
        img.remove();
        wrap.classList.add('fallback-only');
      };
      wrap.appendChild(img);
    }

    const fallback = document.createElement('span');
    fallback.textContent = row.fallback;
    wrap.appendChild(fallback);
    return wrap;
  }

  function openAnalysis(row) {
    if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(row.symbol, row.name);
    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
    else if (typeof window.switchTab === 'function') window.switchTab('chart');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function compactName(row, rect) {
    const constrained = rect.width < 0.2 || rect.height < 0.18;
    if (!constrained) return row.name;
    if (row.name.length <= 7) return row.name;
    return row.symbol.replace(/\.(KS|KQ)$/, '');
  }

  function createTile(rect) {
    const row = rect.row.row;
    const area = rect.width * rect.height;
    const isLarge = area >= 0.11;
    const isMedium = area >= 0.055;
    const showLogo = Boolean(
      row.logo &&
      area >= LOGO_AREA_THRESHOLD &&
      rect.width >= LOGO_MIN_WIDTH &&
      rect.height >= LOGO_MIN_HEIGHT
    );
    const showPrice = Boolean(
      area >= 0.09 &&
      rect.width >= 0.22 &&
      rect.height >= 0.25
    );

    const tile = document.createElement('button');
    tile.type = 'button';
    tile.className = 'cvhm-tile ' + toneClass(row.change) +
      (isLarge ? ' is-large' : isMedium ? ' is-medium' : ' is-small') +
      (rect.width < 0.2 ? ' is-narrow' : '');
    tile.style.left = (rect.x * 100).toFixed(4) + '%';
    tile.style.top = (rect.y * 100).toFixed(4) + '%';
    tile.style.width = (rect.width * 100).toFixed(4) + '%';
    tile.style.height = (rect.height * 100).toFixed(4) + '%';
    tile.dataset.cvhmSymbol = row.symbol;
    tile.title = row.name + ' · ' + signedPercent(row.change) + ' · ' + formatPrice(row.symbol, row.price);
    tile.setAttribute('aria-label', tile.title + ' · 종목 분석 열기');

    const copy = document.createElement('span');
    copy.className = 'cvhm-copy';

    const nameRow = document.createElement('span');
    nameRow.className = 'cvhm-name-row';
    if (showLogo) nameRow.appendChild(makeLogo(row));

    const name = document.createElement('span');
    name.className = 'cvhm-name';
    name.textContent = compactName(row, rect);
    nameRow.appendChild(name);

    const change = document.createElement('strong');
    change.className = 'cvhm-change';
    change.textContent = signedPercent(row.change);

    copy.append(nameRow, change);

    if (showPrice) {
      const price = document.createElement('small');
      price.className = 'cvhm-price';
      price.textContent = formatPrice(row.symbol, row.price);
      copy.appendChild(price);
    }

    tile.appendChild(copy);
    tile.addEventListener('click', () => openAnalysis(row));
    return tile;
  }

  function cssEscape(value) {
    if (window.CSS?.escape) return window.CSS.escape(String(value));
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function cardTone(value) {
    const n = number(value) || 0;
    return n > 0 ? 'up' : n < 0 ? 'down' : 'flat';
  }

  function syncMajorCards(rows) {
    rows.forEach((row) => {
      const card = document.querySelector(
        `#home-tab .home16-stock[data-home-symbol="${cssEscape(row.symbol)}"]`
      );
      if (!card) return;
      const price = card.querySelector('small');
      const change = card.querySelector('b');
      if (price) price.textContent = formatPrice(row.symbol, row.price);
      if (change) {
        change.textContent = signedPercent(row.change);
        change.className = cardTone(row.change);
      }
    });
  }

  function quoteCacheMerge(data) {
    const cache = readJson(QUOTE_CACHE_KEY, { updatedAt: 0, quotes: {} });
    const safe = cache && typeof cache === 'object' ? cache : { updatedAt: 0, quotes: {} };
    if (!safe.quotes || typeof safe.quotes !== 'object') safe.quotes = {};

    (data?.results || []).forEach((item) => {
      const symbol = String(item?.ticker || '').toUpperCase();
      if (!symbol) return;
      const previous = safe.quotes[symbol] && typeof safe.quotes[symbol] === 'object'
        ? safe.quotes[symbol] : {};
      safe.quotes[symbol] = {
        ...previous,
        price: item.price == null ? previous.price ?? null : Number(item.price),
        dayChange: item.change == null ? previous.dayChange ?? null : Number(item.change),
        currency: item.currency || previous.currency || '',
        quoteAsOf: item.asOf || previous.quoteAsOf || '',
        source: item.source || previous.source || data.source || '출처 미확인',
        marketStatus: item.marketStatus ?? previous.marketStatus ?? null,
        delayTime: item.delayTime ?? previous.delayTime ?? null,
        priceBasis: 'latest_provider_quote',
        updatedAt: Date.now(),
      };
    });
    safe.updatedAt = Date.now();
    try { localStorage.setItem(QUOTE_CACHE_KEY, JSON.stringify(safe)); } catch (_) {}
  }

  function marketClock(timeZone) {
    try {
      const parts = new Intl.DateTimeFormat('en-US', {
        timeZone, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
      }).formatToParts(new Date());
      const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      return {
        weekday: map.weekday || '',
        minutes: Number(map.hour || 0) * 60 + Number(map.minute || 0),
      };
    } catch (_) {
      return { weekday: '', minutes: -1 };
    }
  }

  function openMarketSymbols() {
    const symbols = Object.keys(STOCKS);
    const weekdays = new Set(['Mon', 'Tue', 'Wed', 'Thu', 'Fri']);
    const kr = marketClock('Asia/Seoul');
    const us = marketClock('America/New_York');
    const krOpen = weekdays.has(kr.weekday) && kr.minutes >= 9 * 60 && kr.minutes < 15 * 60 + 30;
    const usOpen = weekdays.has(us.weekday) && us.minutes >= 9 * 60 + 30 && us.minutes < 16 * 60;
    if (krOpen && usOpen) return symbols;
    if (krOpen) return symbols.filter((symbol) => STOCKS[symbol].market === 'KR');
    if (usOpen) return symbols.filter((symbol) => STOCKS[symbol].market === 'US');
    return [];
  }

  async function refreshLiveQuotes(forceAll = false) {
    if (!isHomeActive() || document.visibilityState !== 'visible' || navigator.onLine === false || quoteInFlight) return;
    const now = Date.now();
    if (!forceAll && now - lastQuotePollAt < LIVE_QUOTE_POLL_MS) return;

    const symbols = forceAll ? Object.keys(STOCKS) : openMarketSymbols();
    if (!symbols.length) return;
    lastQuotePollAt = now;

    const controller = new AbortController();
    quoteInFlight = controller;
    try {
      const response = await fetch(`/api/quotes?tickers=${encodeURIComponent(symbols.join(','))}`, {
        cache: 'no-store',
        signal: controller.signal,
        headers: { 'X-ChartView-Quote-Mode': 'home-major-live-v65' },
      });
      if (!response.ok) throw new Error('home live quotes HTTP ' + response.status);
      const data = await response.json();
      quoteCacheMerge(data);
      render(cachedPayload());
    } catch (error) {
      if (error?.name !== 'AbortError') console.warn('home live quote refresh failed', error);
    } finally {
      if (quoteInFlight === controller) quoteInFlight = null;
    }
  }

  function renderMarket(container, market, rows) {
    const marketRows = rows
      .filter((row) => row.market === market)
      .filter((row) => row.marketCap > 0)
      .sort((a, b) => b.marketCap - a.marketCap)
      .map((row) => ({ row, weight: relativeWeight(row) }));

    container.replaceChildren();

    if (!marketRows.length) {
      const empty = document.createElement('div');
      empty.className = 'cvhm-empty';
      empty.textContent = '시가총액 데이터를 갱신 중입니다.';
      container.appendChild(empty);
      return;
    }

    const rects = [];
    layout(marketRows, 0, 0, 1, 1, rects);
    rects.forEach((rect) => container.appendChild(createTile(rect)));
  }

  function setView(card, view) {
    const next = view === 'cards' ? 'cards' : 'heatmap';
    const strip = card.querySelector('[data-home-stock-strip]');
    const caption = card.querySelector('.home16-caption');
    const panel = card.querySelector('[data-cvhm-panel]');
    const stripNav = card.querySelector('.home16-strip-nav');

    card.classList.toggle('is-heatmap-view', next === 'heatmap');
    card.querySelectorAll('[data-cvhm-view]').forEach((button) => {
      const active = button.dataset.cvhmView === next;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    if (strip) strip.hidden = next === 'heatmap';
    if (caption) caption.hidden = next === 'heatmap';
    if (panel) panel.hidden = next !== 'heatmap';
    if (stripNav) stripNav.hidden = next === 'heatmap';

    try { localStorage.setItem(VIEW_KEY, next); } catch (_) {}
  }

  function ensureShell() {
    const card = document.querySelector('#home-tab .home16-major-card');
    if (!card) return null;

    let toggle = card.querySelector('[data-cvhm-toggle]');
    if (!toggle) {
      toggle = document.createElement('span');
      toggle.className = 'cvhm-toggle';
      toggle.dataset.cvhmToggle = '';
      [['cards', '카드'], ['heatmap', '히트맵']].forEach(([view, label]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.cvhmView = view;
        button.textContent = label;
        button.addEventListener('click', () => {
          setView(card, view);
          if (view === 'heatmap') {
            render(cachedPayload());
            scheduleRefresh(0);
          }
        });
        toggle.appendChild(button);
      });
      const actions = card.querySelector('.home16-head-actions');
      if (actions) actions.prepend(toggle);
    }

    let panel = card.querySelector('[data-cvhm-panel]');
    if (!panel) {
      panel = document.createElement('div');
      panel.className = 'cvhm-panel';
      panel.dataset.cvhmPanel = '';
      panel.innerHTML =
        '<div class="cvhm-board">' +
          '<section class="cvhm-market"><div class="cvhm-market-head"><strong>🇰🇷 한국 대표</strong><span>KRW 시총 기준 · 시인성 보정</span></div><div class="cvhm-treemap" data-cvhm-market="KR"></div></section>' +
          '<section class="cvhm-market"><div class="cvhm-market-head"><strong>🇺🇸 미국 대표</strong><span>USD 실제 시총 비중</span></div><div class="cvhm-treemap" data-cvhm-market="US"></div></section>' +
        '</div>' +
        '<div class="cvhm-legend"><span><i class="up"></i>상승</span><span><i class="flat"></i>보합</span><span><i class="down"></i>하락</span><small>미국 = 실제 시총 비중 · 한국 = 시총 영향 완화</small></div>';
      const strip = card.querySelector('[data-home-stock-strip]');
      if (strip) strip.insertAdjacentElement('afterend', panel);
      else card.appendChild(panel);
    }

    let preferred = 'heatmap';
    try { preferred = localStorage.getItem(VIEW_KEY) || 'heatmap'; } catch (_) {}
    setView(card, preferred);
    return { card, panel };
  }

  function render(payload) {
    if (!payload?.results?.length) return;
    const shell = ensureShell();
    if (!shell) return;

    const rows = mergedRows(payload);
    if (!rows.length) return;
    syncMajorCards(rows);

    const signature = rows.map((row) => [row.symbol, row.price, row.change, row.marketCap].join(':')).join('|');
    if (signature === lastSignature && shell.panel.dataset.cvhmReady === '1') return;
    lastSignature = signature;

    renderMarket(shell.panel.querySelector('[data-cvhm-market="KR"]'), 'KR', rows);
    renderMarket(shell.panel.querySelector('[data-cvhm-market="US"]'), 'US', rows);
    shell.panel.dataset.cvhmReady = '1';
  }

  async function refresh() {
    if (!isHomeActive() || document.visibilityState !== 'visible' || navigator.onLine === false || inFlight) return;
    const controller = new AbortController();
    inFlight = controller;

    try {
      const response = await fetch('/api/heatmap', { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error('heatmap HTTP ' + response.status);
      const data = await response.json();

      if (data?.results?.length) {
        try { localStorage.setItem(HEATMAP_CACHE_KEY, JSON.stringify(data)); } catch (_) {}
        render(data);

        if (data.results.length < MIN_FULL_ROWS && !retryTimer) {
          retryTimer = setTimeout(() => {
            retryTimer = null;
            refresh();
          }, FAST_RETRY_MS);
        }
      }
    } catch (error) {
      if (error?.name !== 'AbortError') console.warn('home heatmap refresh failed', error);
    } finally {
      if (inFlight === controller) inFlight = null;
    }
  }

  function scheduleRefresh(delay = 180) {
    if (refreshKickTimer) clearTimeout(refreshKickTimer);
    refreshKickTimer = setTimeout(() => {
      refreshKickTimer = null;
      refresh();
    }, delay);
  }

  function start() {
    ensureShell();
    render(cachedPayload());
    refreshLiveQuotes(true);
    scheduleRefresh();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches?.('.home16-major-card') || node.querySelector?.('.home16-major-card')) {
            requestAnimationFrame(() => {
              ensureShell();
              render(cachedPayload());
            });
            return;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    refreshTimer = setInterval(() => {
      if (isHomeActive() && document.visibilityState === 'visible') refresh();
    }, REFRESH_MS);

    setInterval(() => {
      if (isHomeActive() && document.visibilityState === 'visible') refreshLiveQuotes(false);
    }, 1000);

    document.addEventListener('chartview:live-quotes', () => render(cachedPayload()));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') {
        if (inFlight) inFlight.abort();
        if (quoteInFlight) quoteInFlight.abort();
        inFlight = null;
        quoteInFlight = null;
        return;
      }
      if (isHomeActive()) {
        render(cachedPayload());
        refreshLiveQuotes(true);
        scheduleRefresh();
      }
    });
  }

  window.ChartViewHomeHeatmap = Object.freeze({
    version: 'v65',
    refresh,
    refreshLiveQuotes,
    refreshMs: REFRESH_MS,
    liveQuotePollMs: LIVE_QUOTE_POLL_MS
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
