(() => {
  'use strict';

  if (window.ChartViewState?.version === 'v40') return;

  const KEYS = {
    watchlist: 'chartview-watchlist-v1',
    compare: 'chartview-selected-tickers-v1',
    names: 'chartview-ticker-names-v1',
    recents: 'chartview-recents-v1',
  };
  const DEFAULT_COMPARE = ['AAPL', 'NVDA', '005930.KS'];
  const DEFAULT_WATCHLIST = [
    { symbol: '005930.KS', name: '삼성전자' },
    { symbol: 'NVDA', name: '엔비디아' },
    { symbol: 'AAPL', name: '애플' },
  ];

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const normalizeSymbol = (value) => String(value || '').trim().toUpperCase();
  const dedupeSymbols = (rows, max = 6) => {
    const seen = new Set();
    return (Array.isArray(rows) ? rows : [])
      .map(normalizeSymbol)
      .filter((symbol) => symbol && !seen.has(symbol) && seen.add(symbol))
      .slice(0, max);
  };
  const normalizeRows = (rows, max = 20) => {
    const seen = new Set();
    return (Array.isArray(rows) ? rows : []).map((row) => {
      if (!row) return null;
      const symbol = normalizeSymbol(row.symbol || row.ticker);
      if (!symbol || seen.has(symbol)) return null;
      seen.add(symbol);
      return { symbol, name: String(row.name || symbol).trim() || symbol };
    }).filter(Boolean).slice(0, max);
  };

  function readJson(key, fallback) {
    let raw;
    try { raw = localStorage.getItem(key); }
    catch (error) { return { value: clone(fallback), source: 'unavailable', error }; }
    if (raw === null) return { value: clone(fallback), source: 'missing' };
    try { return { value: JSON.parse(raw), source: 'stored' }; }
    catch (error) { return { value: clone(fallback), source: 'invalid', error }; }
  }

  function safeWrite(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      const verify = localStorage.getItem(key);
      if (verify === null) throw new Error('storage verification failed');
      return { ok: true };
    } catch (error) {
      document.dispatchEvent(new CustomEvent('chartview:storage-error', { detail: { key, error: String(error?.message || error) } }));
      return { ok: false, error };
    }
  }

  function getCompare() {
    const result = readJson(KEYS.compare, DEFAULT_COMPARE);
    return { items: dedupeSymbols(result.value, 6), source: result.source };
  }

  function setCompare(items) {
    const next = dedupeSymbols(items, 6);
    const saved = safeWrite(KEYS.compare, next);
    if (saved.ok) document.dispatchEvent(new CustomEvent('chartview:compare-change', { detail: { items: [...next] } }));
    return { ...saved, items: next };
  }

  function getWatchlist() {
    const result = readJson(KEYS.watchlist, DEFAULT_WATCHLIST);
    return { items: normalizeRows(result.value, 20), source: result.source };
  }

  function getNames() {
    const result = readJson(KEYS.names, {});
    return result.value && typeof result.value === 'object' && !Array.isArray(result.value) ? result.value : {};
  }

  function numberState(value) {
    if (value === null || value === undefined || value === '') return { kind: 'missing', value: null };
    const parsed = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(parsed)) return { kind: 'invalid', value: null };
    return { kind: 'number', value: parsed };
  }

  function formatNumber(value, options = {}) {
    const state = numberState(value);
    if (state.kind !== 'number') return options.missing || '—';
    const digits = Number.isInteger(options.digits) ? options.digits : 1;
    const suffix = options.suffix || '';
    const prefix = options.prefix || '';
    const sign = options.sign && state.value > 0 ? '+' : '';
    return `${prefix}${sign}${state.value.toLocaleString(options.locale || 'ko-KR', { minimumFractionDigits: options.minDigits ?? 0, maximumFractionDigits: digits })}${suffix}`;
  }

  function formatPercent(value, digits = 1) {
    return formatNumber(value, { digits, suffix: '%', sign: true });
  }

  function formatMultiple(value, digits = 1) {
    const state = numberState(value);
    return state.kind === 'number' ? `${state.value.toFixed(digits)}x` : '—';
  }

  function formatPrice(symbol, value) {
    const state = numberState(value);
    if (state.kind !== 'number') return '—';
    if (/\.(KS|KQ)$/.test(symbol)) return `₩${Math.round(state.value).toLocaleString('ko-KR')}`;
    return `$${state.value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function calcRevision(current, prior) {
    const a = numberState(current), b = numberState(prior);
    if (a.kind !== 'number' || b.kind !== 'number') return { kind: 'missing', value: null };
    if (b.value === 0) return { kind: 'unavailable', value: null, reason: '분모 0' };
    return { kind: 'number', value: (a.value / b.value - 1) * 100 };
  }

  function captureScreen() {
    const activeTab = document.querySelector('.tab-content.active')?.id?.replace(/-tab$/, '') || history.state?.tab || 'home';
    const controls = {};
    document.querySelectorAll('.tab-content.active input, .tab-content.active select').forEach((el) => {
      const key = el.id || el.name;
      if (key) controls[key] = el.value;
    });
    return {
      tab: activeTab,
      scrollY: window.scrollY,
      controls,
      capturedAt: Date.now(),
    };
  }

  function restoreScreen(snapshot) {
    if (!snapshot) return;
    if (snapshot.tab && typeof window.__openAppTab === 'function') window.__openAppTab(snapshot.tab, { history: false });
    Object.entries(snapshot.controls || {}).forEach(([key, value]) => {
      const el = document.getElementById(key) || document.querySelector(`[name="${CSS.escape(key)}"]`);
      if (el && el.value !== value) el.value = value;
    });
    requestAnimationFrame(() => window.scrollTo({ top: Number(snapshot.scrollY) || 0, behavior: 'auto' }));
  }

  const detail = { open: false, symbol: '', name: '', seq: 0 };
  function beginDetail(symbol, name) {
    detail.open = true;
    detail.symbol = normalizeSymbol(symbol);
    detail.name = String(name || detail.symbol);
    detail.seq += 1;
    return { ...detail };
  }
  function closeDetail() {
    detail.open = false;
    detail.seq += 1;
    return { ...detail };
  }
  function isCurrentDetail(symbol, seq) {
    return detail.open && detail.symbol === normalizeSymbol(symbol) && detail.seq === seq;
  }

  let syncTimer = null;
  function syncLegacyCompare() {
    const compare = getCompare().items;
    let changed = false;
    try {
      if (typeof selectedTickers !== 'undefined' && JSON.stringify(selectedTickers) !== JSON.stringify(compare)) {
        selectedTickers = [...compare];
        changed = true;
      }
      if (typeof perTickers !== 'undefined' && JSON.stringify(perTickers) !== JSON.stringify(compare)) {
        perTickers = [...compare];
        changed = true;
      }
      const names = getNames();
      if (typeof tickerNameMap !== 'undefined') Object.assign(tickerNameMap, names);
      if (typeof perTickerNameMap !== 'undefined') Object.assign(perTickerNameMap, names);
      if (changed && typeof updateTags === 'function') updateTags();
      if (changed && typeof loadData === 'function') loadData();
      if (changed && typeof loadPerData === 'function' && document.getElementById('fwdper-tab')?.classList.contains('active')) loadPerData();
    } catch (_) { }
  }

  function scheduleLegacySync() {
    clearTimeout(syncTimer);
    syncTimer = setTimeout(syncLegacyCompare, 0);
  }

  window.ChartViewData = {
    numberState, formatNumber, formatPercent, formatMultiple, formatPrice, calcRevision,
  };
  window.ChartViewState = {
    version: 'v40', KEYS, DEFAULT_COMPARE: [...DEFAULT_COMPARE], DEFAULT_WATCHLIST: clone(DEFAULT_WATCHLIST),
    getCompare, setCompare, getWatchlist, getNames, safeWrite,
    captureScreen, restoreScreen, beginDetail, closeDetail, isCurrentDetail,
    syncLegacyCompare: scheduleLegacySync,
    detail,
  };

  document.addEventListener('chartview:compare-change', scheduleLegacySync);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scheduleLegacySync, { once: true });
  else scheduleLegacySync();
  setTimeout(scheduleLegacySync, 400);
  setTimeout(scheduleLegacySync, 1400);
})();
