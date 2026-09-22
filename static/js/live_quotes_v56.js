(() => {
  'use strict';

  // OpenStock-inspired interaction model: cache-first paint + lightweight polling.
  // This module is original Chart View code; it never triggers historical returns.
  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const QUOTE_CACHE_KEY = 'chartview-watchlist-quotes-v33';
  const WATCHLIST_POLL_MS = 5000;
  const CLOSED_MARKET_POLL_MS = 30000;
  const GLOBAL_POLL_MS = 30000;
  const HOME_POLL_MS = 30000;
  const MAX_BATCH = 20;

  let inFlight = null;
  let requestSeq = 0;
  let lastKrPollAt = 0;
  let lastGlobalPollAt = 0;
  let lastHomePollAt = 0;
  let krMarketOpen = null;

  const isKorean = (symbol) => /\.(KS|KQ)$/.test(String(symbol || '').toUpperCase());
  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, '\\$&');
  };

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function watchlist() {
    const rows = readJson(WATCHLIST_KEY, []);
    const seen = new Set();
    return (Array.isArray(rows) ? rows : [])
      .map((row) => ({
        symbol: String(row?.symbol || row?.ticker || '').trim().toUpperCase(),
        name: String(row?.name || row?.symbol || row?.ticker || '').trim(),
      }))
      .filter((row) => row.symbol && !seen.has(row.symbol) && seen.add(row.symbol))
      .slice(0, MAX_BATCH);
  }

  function activeMode() {
    if (document.getElementById('watchlist-tab')?.classList.contains('active')) return 'watchlist';
    if (document.getElementById('home-tab')?.classList.contains('active')) return 'home';
    return '';
  }

  function visibleWatchSymbols(rows) {
    const allowed = new Set(rows.map((row) => row.symbol));
    const visible = [];
    document.querySelectorAll('[data-watch-card]').forEach((card) => {
      const symbol = String(card.dataset.watchCard || '').toUpperCase();
      if (!allowed.has(symbol)) return;
      const rect = card.getBoundingClientRect();
      if (rect.bottom >= 0 && rect.top <= window.innerHeight) visible.push(symbol);
    });
    return visible.length ? visible.slice(0, 8) : rows.slice(0, 4).map((row) => row.symbol);
  }

  function homeSymbols(rows) {
    const visible = [];
    document.querySelectorAll('[data-home-watch-open]').forEach((node) => {
      const symbol = String(node.dataset.homeWatchOpen || '').toUpperCase();
      if (symbol) visible.push(symbol);
    });
    return visible.length ? [...new Set(visible)].slice(0, 4) : rows.slice(0, 4).map((row) => row.symbol);
  }

  function dueSymbols(symbols, mode, now) {
    if (mode === 'home') {
      if (now - lastHomePollAt < HOME_POLL_MS) return [];
      lastHomePollAt = now;
      return symbols;
    }

    const korean = symbols.filter(isKorean);
    const global = symbols.filter((symbol) => !isKorean(symbol));
    const krInterval = krMarketOpen === false ? CLOSED_MARKET_POLL_MS : WATCHLIST_POLL_MS;
    const dueKr = now - lastKrPollAt >= krInterval ? korean : [];
    const dueGlobal = now - lastGlobalPollAt >= GLOBAL_POLL_MS ? global : [];
    if (dueKr.length) lastKrPollAt = now;
    if (dueGlobal.length) lastGlobalPollAt = now;
    return [...dueKr, ...dueGlobal].slice(0, MAX_BATCH);
  }

  function formatPrice(symbol, value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return null;
    if (isKorean(symbol)) return `₩${Math.round(number).toLocaleString('ko-KR')}`;
    return `$${number.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function signedPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return null;
    return `${number > 0 ? '+' : ''}${number.toFixed(2)}%`;
  }

  function directionClass(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number === 0) return 'flat';
    return number > 0 ? 'up' : 'down';
  }

  function timeLabel(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    try {
      return new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(date);
    } catch (_) {
      return '';
    }
  }

  function ensureLiveLine(card) {
    let line = card.querySelector('[data-watch-live-line]');
    if (line) return line;
    line = document.createElement('span');
    line.className = 'watchlist-live-line';
    line.dataset.watchLiveLine = '';
    line.innerHTML = '<b data-live-day-change>오늘 —</b><i data-live-state>최근 시세</i>';
    const quote = card.querySelector('.watchlist-v30-quote');
    if (quote) quote.insertAdjacentElement('afterend', line);
    else card.appendChild(line);
    return line;
  }

  function ensureHomeDay(node) {
    let day = node.querySelector('[data-home-live-day-change]');
    if (day) return day;
    day = document.createElement('small');
    day.className = 'home-live-day-change';
    day.dataset.homeLiveDayChange = '';
    const quote = node.querySelector('.home-watch-v33-quote');
    if (quote) quote.insertAdjacentElement('afterend', day);
    else node.appendChild(day);
    return day;
  }

  function liveState(item) {
    const status = String(item?.marketStatus || '').toUpperCase();
    const delay = Number(item?.delayTime);
    if (isKorean(item?.ticker) && status === 'OPEN' && (!Number.isFinite(delay) || delay === 0)) return '실시간';
    return '최근 시세';
  }

  function paintQuote(item, previousPrice) {
    const symbol = String(item?.ticker || '').toUpperCase();
    if (!symbol) return;

    const card = document.querySelector(`[data-watch-card="${cssEscape(symbol)}"]`);
    if (card) {
      const price = card.querySelector('[data-watch-price]');
      const formatted = formatPrice(symbol, item.price);
      if (price && formatted) {
        if (Number.isFinite(Number(previousPrice)) && Number(previousPrice) !== Number(item.price)) {
          price.classList.remove('live-price-flash');
          void price.offsetWidth;
          price.classList.add('live-price-flash');
        }
        price.textContent = formatted;
      }
      const line = ensureLiveLine(card);
      const change = line.querySelector('[data-live-day-change]');
      const state = line.querySelector('[data-live-state]');
      const dayText = signedPercent(item.change);
      if (change) {
        change.textContent = dayText ? `오늘 ${dayText}` : '오늘 —';
        change.className = directionClass(item.change);
      }
      if (state) {
        const label = liveState(item);
        const at = timeLabel(item.asOf);
        state.textContent = at ? `${label} · ${at}` : label;
        state.classList.toggle('live', label === '실시간');
        state.title = item.source || '';
      }
    }

    const home = document.querySelector(`[data-home-watch-open="${cssEscape(symbol)}"]`);
    if (home) {
      const price = home.querySelector('[data-home-watch-price]');
      const formatted = formatPrice(symbol, item.price);
      if (price && formatted) price.textContent = formatted;
      const day = ensureHomeDay(home);
      const dayText = signedPercent(item.change);
      day.textContent = dayText ? `오늘 ${dayText}` : '';
      day.className = `home-live-day-change ${directionClass(item.change)}`;
    }
  }

  function mergeCache(data) {
    const cache = readJson(QUOTE_CACHE_KEY, { updatedAt: 0, quotes: {} });
    const safe = cache && typeof cache === 'object' ? cache : { updatedAt: 0, quotes: {} };
    if (!safe.quotes || typeof safe.quotes !== 'object') safe.quotes = {};

    (data.results || []).forEach((item) => {
      const symbol = String(item?.ticker || '').toUpperCase();
      if (!symbol) return;
      const previous = safe.quotes[symbol] && typeof safe.quotes[symbol] === 'object' ? safe.quotes[symbol] : {};
      paintQuote(item, previous.price);
      safe.quotes[symbol] = {
        ...previous,
        price: item.price == null ? previous.price ?? null : Number(item.price),
        dayChange: item.change == null ? previous.dayChange ?? null : Number(item.change),
        currency: item.currency || previous.currency || '',
        quoteAsOf: item.asOf || previous.quoteAsOf || '',
        receivedAt: data.fetchedAt || previous.receivedAt || '',
        source: item.source || previous.source || data.source || '출처 미확인',
        marketStatus: item.marketStatus ?? previous.marketStatus ?? null,
        delayTime: item.delayTime ?? previous.delayTime ?? null,
        priceBasis: 'latest_provider_quote',
        updatedAt: Date.now(),
      };
    });
    safe.updatedAt = Date.now();
    try { localStorage.setItem(QUOTE_CACHE_KEY, JSON.stringify(safe)); } catch (_) { }

    const krRows = (data.results || []).filter((item) => isKorean(item?.ticker));
    if (krRows.length) {
      krMarketOpen = krRows.some((item) => String(item.marketStatus || '').toUpperCase() === 'OPEN');
    }
  }

  async function refreshActiveQuotes({ force = false, fullWatchlist = false } = {}) {
    if (document.visibilityState !== 'visible' || navigator.onLine === false) return;
    const mode = activeMode();
    if (!mode) return;
    const rows = watchlist();
    if (!rows.length) return;

    const base = mode === 'watchlist'
      ? (fullWatchlist ? rows.map((row) => row.symbol) : visibleWatchSymbols(rows))
      : homeSymbols(rows);
    const symbols = force ? base : dueSymbols(base, mode, Date.now());
    if (!symbols.length || inFlight) return;

    const seq = ++requestSeq;
    const controller = new AbortController();
    inFlight = controller;
    try {
      const response = await fetch(`/api/quotes?tickers=${encodeURIComponent(symbols.join(','))}`, {
        cache: 'no-store',
        signal: controller.signal,
        headers: { 'X-ChartView-Quote-Mode': fullWatchlist ? 'watchlist-bootstrap-v64' : 'live-visible-v64' },
      });
      if (!response.ok) throw new Error(`quotes ${response.status}`);
      const data = await response.json();
      if (seq !== requestSeq) return;
      mergeCache(data);
      document.dispatchEvent(new CustomEvent('chartview:live-quotes', {
        detail: { symbols, fetchedAt: data.fetchedAt || '', mode },
      }));
    } catch (error) {
      if (error?.name !== 'AbortError') {
        document.dispatchEvent(new CustomEvent('chartview:live-quotes-error', {
          detail: { symbols, message: String(error?.message || error) },
        }));
      }
    } finally {
      if (inFlight === controller) inFlight = null;
    }
  }

  function abortIfInactive() {
    if (activeMode()) return;
    if (inFlight) inFlight.abort();
    inFlight = null;
  }

  function enhanceCachedRows() {
    const cache = readJson(QUOTE_CACHE_KEY, { quotes: {} });
    const quotes = cache?.quotes && typeof cache.quotes === 'object' ? cache.quotes : {};
    watchlist().forEach((row) => {
      const card = document.querySelector(`[data-watch-card="${cssEscape(row.symbol)}"]`);
      if (card) ensureLiveLine(card);
      const quote = quotes[row.symbol];
      if (!quote) return;
      paintQuote({
        ticker: row.symbol,
        price: quote.price,
        change: quote.dayChange,
        asOf: quote.quoteAsOf,
        source: quote.source,
        marketStatus: quote.marketStatus,
        delayTime: quote.delayTime,
      }, quote.price);
    });
  }

  let lastMode = '';

  async function tick(force = false) {
    const mode = activeMode();
    const modeChanged = mode !== lastMode;

    if (modeChanged) {
      lastMode = mode;
      if (!mode) {
        abortIfInactive();
        return;
      }
      enhanceCachedRows();
      // Home already has its own cache-first boot refresh. Avoid duplicating it.
      if (mode === 'home') lastHomePollAt = Date.now();
    }

    if (!mode) return;
    const bootstrapAll = modeChanged && mode === 'watchlist';
    await refreshActiveQuotes({
      force: force || bootstrapAll,
      fullWatchlist: bootstrapAll,
    });
  }

  function start() {
    enhanceCachedRows();
    lastMode = '';
    setTimeout(() => tick(false), 0);
    setInterval(() => tick(false), 1000);

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') {
        if (inFlight) inFlight.abort();
        inFlight = null;
        return;
      }
      enhanceCachedRows();
      setTimeout(() => tick(activeMode() === 'watchlist'), 150);
    });

    window.addEventListener('online', () => setTimeout(() => tick(activeMode() === 'watchlist'), 100));
    document.addEventListener('chartview:watchlist-change', enhanceCachedRows);

    let enhanceQueued = false;
    const scheduleEnhance = () => {
      if (enhanceQueued) return;
      enhanceQueued = true;
      requestAnimationFrame(() => {
        enhanceQueued = false;
        enhanceCachedRows();
      });
    };
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (
            node.matches?.('[data-watch-card], [data-home-watch-open]')
            || node.querySelector?.('[data-watch-card], [data-home-watch-open]')
          ) {
            scheduleEnhance();
            return;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.ChartViewLiveQuotes = Object.freeze({
    version: 'v64',
    refresh: () => refreshActiveQuotes({ force: true }),
    watchlistPollMs: WATCHLIST_POLL_MS,
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
