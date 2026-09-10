// Field-level valuation provenance for transparency.
(() => {
  'use strict';

  let cachePromise = null;
  const ymd = (value) => {
    if (!value) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
    return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\. /g, '.').replace(/\.$/, '');
  };
  const today = () => ymd(new Date());

  function loadQuoteCache() {
    if (!cachePromise) {
      cachePromise = fetch('/static/data/valuation_cache.json', { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : { quotes: {} })
        .catch(() => ({ quotes: {} }));
    }
    return cachePromise;
  }

  function present(v) {
    return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  }

  const cacheField = {
    price: 'regularMarketPrice', marketCap: 'marketCap', trailingPE: 'trailingPE', forwardPE: 'forwardPE',
    trailingEPS: 'epsTrailingTwelveMonths', forwardEPS: 'epsForward', pbr: 'priceToBook', bookValue: 'bookValue',
    dividendYield: 'dividendYield',
  };

  function provenance(stock, key, quoteRow, generatedAt) {
    const cacheKey = cacheField[key];
    const cacheHas = cacheKey && quoteRow && present(quoteRow[cacheKey]);
    const cacheDate = ymd(generatedAt) || today();
    const sourceText = String(stock.dataSource || '');
    const isKR = /\.(KS|KQ)$/.test(stock.ticker || '');

    if (cacheHas) {
      if (key === 'forwardPE' || key === 'forwardEPS') return `${cacheDate} · 12M 전망 · Yahoo 컨센서스 캐시`;
      if (key === 'dividendYield') return `${cacheDate} · 최근 배당 · Yahoo 일일 캐시`;
      return `${cacheDate} · Yahoo 일일 캐시`;
    }
    if ((key === 'forwardPE' || key === 'forwardEPS') && !present(stock[key])) return '12M 전망 · 컨센서스 데이터 없음';
    if (key === 'forwardPE' || key === 'forwardEPS') return `12M 전망 · ${today()} 조회 · Yahoo QuoteSummary`;
    if (key === 'price') return `${today()} 조회 · Yahoo Chart`;
    if ((key === 'trailingPE' || key === 'pbr' || key === 'dividendYield') && isKR && sourceText.includes('Naver')) return `${today()} 조회 · Naver Finance`;
    if (key === 'trailingPE' || key === 'trailingEPS' || key === 'psr') return `TTM · ${today()} 조회 · Yahoo Fundamentals`;
    if (key === 'pbr' || key === 'bookValue') return `최근 공시 · ${today()} 조회 · Yahoo Fundamentals`;
    if (key === 'evEbitda' || key === 'roe' || key === 'operatingMargin') return `TTM/최근 공시 · ${today()} 조회 · Yahoo Fundamentals`;
    if (key === 'dividendYield') return `최근 배당 · ${today()} 조회 · Yahoo/Naver`;
    if (key === 'marketCap') return `${today()} 조회 · Yahoo Fundamentals`;
    return `${today()} 조회 · ${sourceText || 'Yahoo Finance'}`;
  }

  function ensureValueWrap(cell) {
    let wrap = cell.querySelector(':scope > .metric-value-wrap');
    if (wrap) return wrap;
    const rawText = Array.from(cell.childNodes)
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => n.textContent || '')
      .join('')
      .trim();
    Array.from(cell.childNodes).forEach((n) => n.remove());
    wrap = document.createElement('div');
    wrap.className = 'metric-value-wrap';
    const value = document.createElement('div');
    value.className = 'metric-value-main';
    value.textContent = rawText || '-';
    const meta = document.createElement('div');
    meta.className = 'metric-provenance';
    wrap.append(value, meta);
    cell.appendChild(wrap);
    return wrap;
  }

  async function annotateTable() {
    const table = document.querySelector('#per-table-container .per-table');
    if (!table || typeof perData === 'undefined' || typeof METRIC_CONFIG === 'undefined') return;

    const payload = await loadQuoteCache();
    const quotes = payload.quotes || {};
    const config = METRIC_CONFIG[currentMetric] || METRIC_CONFIG.overview;
    const keys = ['stock', 'price', ...config.columns.map((c) => c.key)];
    const headers = ['종목', '현재가', ...config.columns.map((c) => c.label)];

    table.querySelectorAll('tbody tr').forEach((row) => {
      const ticker = row.querySelector('.stock-ticker')?.textContent?.trim();
      const stock = perData.find((s) => s.ticker === ticker);
      if (!stock) return;
      const quoteRow = quotes[ticker] || null;
      Array.from(row.children).forEach((cell, index) => {
        cell.dataset.label = headers[index] || '';
        if (index === 0) return;
        const key = keys[index];
        const wrap = ensureValueWrap(cell);
        const meta = wrap.querySelector('.metric-provenance');
        const text = provenance(stock, key, quoteRow, payload.generatedAt);
        if (meta && meta.textContent !== text) meta.textContent = text;
      });
    });

    const src = document.querySelector('.per-source');
    if (src) src.textContent = '각 수치 아래에 데이터 기준과 출처를 표시합니다 · 없는 값은 - 표시';
  }

  function init() {
    const target = document.getElementById('per-table-container');
    if (!target) return;
    annotateTable();
    let queued = false;
    const observer = new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        annotateTable();
      });
    });
    observer.observe(target, { childList: true, subtree: true });
    document.querySelectorAll('.metric-chip, .sort-btn').forEach((el) => el.addEventListener('click', () => setTimeout(annotateTable, 0)));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
