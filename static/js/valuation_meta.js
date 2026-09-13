// Field-level valuation provenance for transparency without sacrificing mobile comparison density.
(() => {
  'use strict';

  let cachePromise = null;
  const MOBILE_BREAKPOINT = 720;
  const ymd = (value) => {
    if (!value) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
    return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\. /g, '.').replace(/\.$/, '');
  };
  const today = () => ymd(new Date());
  const compactMode = () => window.matchMedia(`(max-width:${MOBILE_BREAKPOINT}px)`).matches;

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
    const exact = stock?.fieldMeta?.[key];
    if (!present(stock?.[key])) {
      if (key === 'forwardPE' || key === 'forwardEPS') return '예상 기간 미확인 · 컨센서스 데이터 없음';
      return `${exact?.period || '해당 지표'} · 데이터 없음`;
    }
    if (exact?.source) {
      const asOf = ymd(exact.asOf);
      const periodMap = {
        'provider forward period (not independently verified)': '예상 기간 미확인',
        'latest trading value': '최근 거래값',
        'latest available': '최근 자료',
        'latest reported': '최근 공시',
        'latest indicated/reported': '최근 배당',
        'TTM/latest reported': 'TTM/최근 공시',
      };
      const period = periodMap[exact.period] || exact.period || '';
      const method = exact.method && exact.method !== 'provider' ? ` · ${exact.method}` : '';
      return [asOf, period, exact.source].filter(Boolean).join(' · ') + method;
    }
    const cacheKey = cacheField[key];
    const cacheHas = cacheKey && quoteRow && present(quoteRow[cacheKey]);
    const cacheDate = ymd(generatedAt) || today();
    const sourceText = String(stock.dataSource || '');
    const isKR = /\.(KS|KQ)$/.test(stock.ticker || '');

    if (cacheHas) {
      if (key === 'forwardPE' || key === 'forwardEPS') return `${cacheDate} · 예상 기간 미확인 · Yahoo 컨센서스 캐시`;
      if (key === 'dividendYield') return `${cacheDate} · 최근 배당 · Yahoo 일일 캐시`;
      return `${cacheDate} · Yahoo 일일 캐시`;
    }
    if ((key === 'forwardPE' || key === 'forwardEPS') && !present(stock[key])) return '예상 기간 미확인 · 컨센서스 데이터 없음';
    if (key === 'forwardPE' || key === 'forwardEPS') return `예상 기간 미확인 · ${today()} 조회 · Yahoo QuoteSummary`;
    if (key === 'price') return `${today()} 조회 · Yahoo Chart`;
    if ((key === 'trailingPE' || key === 'pbr' || key === 'dividendYield') && isKR && sourceText.includes('Naver')) return `${today()} 조회 · Naver Finance`;
    if (key === 'trailingPE' || key === 'trailingEPS' || key === 'psr') return `TTM · ${today()} 조회 · Yahoo Fundamentals`;
    if (key === 'pbr' || key === 'bookValue') return `최근 공시 · ${today()} 조회 · Yahoo Fundamentals`;
    if (key === 'evEbitda' || key === 'roe' || key === 'operatingMargin') return `TTM/최근 공시 · ${today()} 조회 · Yahoo Fundamentals`;
    if (key === 'dividendYield') return `최근 배당 · ${today()} 조회 · Yahoo/Naver`;
    if (key === 'marketCap') return `${today()} 조회 · Yahoo Fundamentals`;
    return `${today()} 조회 · ${sourceText || 'Yahoo Finance'}`;
  }

  function rawCellText(cell) {
    const main = cell.querySelector(':scope > .metric-value-wrap > .metric-value-main');
    if (main) return main.textContent?.trim() || '-';
    return Array.from(cell.childNodes)
      .filter((node) => {
        if (node.nodeType === Node.TEXT_NODE) return true;
        if (node.nodeType !== Node.ELEMENT_NODE) return false;
        return !node.classList?.contains('metric-provenance')
          && !node.classList?.contains('v40-cell-basis')
          && !node.matches?.('[data-valuation-basis]');
      })
      .map((node) => node.textContent || '')
      .join('')
      .trim() || '-';
  }

  function formatCompactValue(stock, key, column) {
    const isKR = /\.(KS|KQ)$/.test(stock?.ticker || '');
    if (key === 'price') {
      const value = Number(stock?.price);
      if (!Number.isFinite(value) || value <= 0) return '-';
      return isKR
        ? `₩${Math.round(value).toLocaleString('ko-KR')}`
        : `$${value.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}`;
    }
    if (!column) return '-';
    if (typeof formatValue === 'function') {
      try { return formatValue(stock?.[key], column.format, isKR); } catch (_) { }
    }
    const value = Number(stock?.[key]);
    if (!Number.isFinite(value)) return '-';
    if (column.format === 'percent') return `${value.toFixed(2)}%`;
    return value.toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
  }

  function ensureValueWrap(cell) {
    let wrap = cell.querySelector(':scope > .metric-value-wrap');
    if (wrap) return wrap;
    const text = rawCellText(cell);
    cell.replaceChildren();
    wrap = document.createElement('div');
    wrap.className = 'metric-value-wrap';
    const value = document.createElement('div');
    value.className = 'metric-value-main';
    value.textContent = text;
    const meta = document.createElement('div');
    meta.className = 'metric-provenance';
    wrap.append(value, meta);
    cell.appendChild(wrap);
    return wrap;
  }

  function applyCompactCell(cell, provenanceText, valueText) {
    // Mobile cards show only the value. Provenance is metadata, never visible
    // cell content. This must remain idempotent because the table is observed.
    const desired = String(valueText || '-').trim() || '-';
    const hasUnexpectedChildren = cell.children.length > 0;
    const current = cell.textContent?.trim() || '';
    if (hasUnexpectedChildren || current !== desired) {
      cell.replaceChildren(document.createTextNode(desired));
    }
    cell.dataset.provenance = provenanceText;
    cell.title = provenanceText;
    cell.classList.add('valuation-compact-cell');
  }

  async function annotateTable() {
    const table = document.querySelector('#per-table-container .per-table');
    if (!table || typeof perData === 'undefined' || typeof METRIC_CONFIG === 'undefined') return;

    const payload = await loadQuoteCache();
    const quotes = payload.quotes || {};
    const config = METRIC_CONFIG[currentMetric] || METRIC_CONFIG.overview;
    const keys = ['stock', 'price', ...config.columns.map((c) => c.key)];
    const headers = ['종목', '현재가', ...config.columns.map((c) => c.label)];
    const compact = compactMode();

    table.classList.toggle('valuation-compact-table', compact);
    table.querySelectorAll('tbody tr').forEach((row) => {
      const ticker = row.querySelector('.stock-ticker')?.textContent?.trim();
      const stock = perData.find((s) => s.ticker === ticker);
      if (!stock) return;
      const quoteRow = quotes[ticker] || null;
      Array.from(row.children).forEach((cell, index) => {
        cell.dataset.label = headers[index] || '';
        if (index === 0) return;
        const key = keys[index];
        const text = provenance(stock, key, quoteRow, payload.generatedAt);
        if (compact) {
          const column = index >= 2 ? config.columns[index - 2] : null;
          applyCompactCell(cell, text, formatCompactValue(stock, key, column));
        } else {
          cell.classList.remove('valuation-compact-cell');
          cell.removeAttribute('title');
          const wrap = ensureValueWrap(cell);
          const meta = wrap.querySelector('.metric-provenance');
          if (meta && meta.textContent !== text) meta.textContent = text;
        }
      });
    });

    const src = document.querySelector('.per-source');
    if (src) {
      const date = ymd(payload.generatedAt) || today();
      const wanted = compact
        ? `${date} 기준 · 가격/컨센서스: Yahoo 캐시 · 재무지표: Yahoo Fundamentals/Naver 보완 · 셀별 출처는 길게 눌러 확인`
        : '각 수치 아래에 데이터 기준과 출처를 표시합니다 · 없는 값은 - 표시';
      if (src.textContent !== wanted) src.textContent = wanted;
    }
  }

  function init() {
    const target = document.getElementById('per-table-container');
    if (!target) return;
    annotateTable();
    let queued = false;
    const queue = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        annotateTable();
      });
    };
    const observer = new MutationObserver(queue);
    observer.observe(target, { childList: true, subtree: true });
    document.querySelectorAll('.metric-chip, .sort-btn').forEach((el) => el.addEventListener('click', () => setTimeout(annotateTable, 0)));
    window.addEventListener('resize', queue, { passive: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
