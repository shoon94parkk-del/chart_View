// UX/performance patch: fast screener + instant Korean stock search.
(() => {
  'use strict';

  if (!document.querySelector('link[data-fast-screener]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/css/screener.css?v=20260910v2';
    link.dataset.fastScreener = '1';
    document.head.appendChild(link);
  }
  if (!document.querySelector('script[data-fast-screener]')) {
    const script = document.createElement('script');
    script.src = '/static/js/screener.js?v=20260910v2';
    script.dataset.fastScreener = '1';
    document.head.appendChild(script);
  }

  const aliases = {
    '삼전': '삼성전자', '하닉': 'SK하이닉스', '삼바': '삼성바이오로직스',
    '엘전': 'LG전자', '현차': '현대차', '네이버': 'NAVER'
  };

  let universePromise = null;
  let localTimer = null;

  const hasKorean = (text) => /[가-힣]/.test(text);
  const isSixCharCode = (text) => /^[0-9A-Za-z]{6}$/.test(text);
  const isTickerLike = (text) => /^[A-Z][A-Z0-9.-]{0,9}$/.test(text);

  function loadUniverse() {
    if (!universePromise) {
      universePromise = fetch('/static/data/screener.json', { cache: 'force-cache' })
        .then((res) => {
          if (!res.ok) throw new Error(`screener HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          const rows = Array.isArray(data.stocks) ? data.stocks : [];
          window.__KRX_UNIVERSE__ = rows;
          return rows;
        })
        .catch((err) => {
          console.warn('Local Korean universe unavailable; falling back to server search.', err);
          return [];
        });
    }
    return universePromise;
  }

  function normalizeQuery(raw) {
    const q = raw.trim();
    return aliases[q.toLowerCase()] || q;
  }

  function wantsLocalSearch(raw) {
    const q = raw.trim();
    return hasKorean(q) || isSixCharCode(q) || Object.prototype.hasOwnProperty.call(aliases, q.toLowerCase());
  }

  function rankKorean(rows, raw) {
    const query = normalizeQuery(raw);
    const q = query.toLowerCase();
    return rows
      .map((row) => {
        const name = String(row.name || '');
        const code = String(row.code || '');
        const nameLower = name.toLowerCase();
        let score = -1;
        if (code.toLowerCase() === q || nameLower === q) score = 100;
        else if (nameLower.startsWith(q)) score = 80;
        else if (nameLower.includes(q)) score = 60;
        else if (code.toLowerCase().startsWith(q)) score = 50;
        return { row, score };
      })
      .filter((x) => x.score >= 0)
      .sort((a, b) => b.score - a.score || (b.row.avgValue20 || 0) - (a.row.avgValue20 || 0))
      .slice(0, 10)
      .map((x) => x.row);
  }

  function renderLocalResults(rows, raw) {
    const box = document.getElementById('search-results');
    if (!box) return;

    if (!rows.length) {
      box.innerHTML = `<div class="search-result-item"><span class="name">검색 결과 없음</span><span class="symbol">${raw}</span></div>`;
      box.classList.remove('hidden');
      return;
    }

    box.innerHTML = '';
    rows.forEach((row) => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = `<span class="name"></span><span class="symbol"></span>`;
      item.querySelector('.name').textContent = row.name || row.symbol;
      item.querySelector('.symbol').textContent = `${row.code || row.symbol} · ${row.market || 'KRX'}`;
      item.addEventListener('click', () => {
        if (typeof window.selectSearchResult === 'function') {
          window.selectSearchResult(row.symbol, row.name || row.symbol);
        }
      });
      box.appendChild(item);
    });
    box.classList.remove('hidden');
  }

  async function addBestLocal(raw) {
    const rows = rankKorean(await loadUniverse(), raw);
    if (rows[0] && typeof window.selectSearchResult === 'function') {
      window.selectSearchResult(rows[0].symbol, rows[0].name || rows[0].symbol);
      return true;
    }
    return false;
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Preload the ~2,600-stock universe once. All Korean autocomplete after this is browser-side.
    loadUniverse();

    const sector = document.querySelector('.sector-section');
    if (sector && !sector.querySelector('.ux-sector-toggle')) {
      const toggle = document.createElement('button');
      toggle.className = 'ux-sector-toggle';
      toggle.type = 'button';
      toggle.innerHTML = '<span>추천 종목</span><span class="ux-sector-arrow">펼치기 ↓</span>';
      sector.insertBefore(toggle, sector.firstChild);
      sector.classList.add('ux-collapsed');
      toggle.addEventListener('click', () => {
        const collapsed = sector.classList.toggle('ux-collapsed');
        toggle.querySelector('.ux-sector-arrow').textContent = collapsed ? '펼치기 ↓' : '접기 ↑';
      });
    }

    const chartHeader = document.querySelector('.chart-header');
    if (chartHeader && !document.querySelector('.ux-data-status')) {
      const status = document.createElement('div');
      status.className = 'ux-data-status';
      status.textContent = '차트: Yahoo Finance · 한국 종목 검색/스크리너: 장 마감 배치 데이터 · 국내 시세는 지연될 수 있습니다.';
      chartHeader.insertAdjacentElement('afterend', status);
    }

    const input = document.getElementById('unified-input');
    const box = document.getElementById('search-results');
    const addButton = document.getElementById('add-btn');
    if (!input || !box) return;

    input.setAttribute('aria-label', '종목명, 6자리 종목코드 또는 해외 티커 검색');

    // Capture phase runs before the legacy server-search listener in chart.js.
    input.addEventListener('input', (event) => {
      const raw = input.value.trim();
      if (!wantsLocalSearch(raw)) return;
      event.stopImmediatePropagation();
      clearTimeout(localTimer);
      if (!raw) {
        box.classList.add('hidden');
        return;
      }
      localTimer = setTimeout(async () => {
        renderLocalResults(rankKorean(await loadUniverse(), raw), raw);
      }, 60);
    }, true);

    input.addEventListener('keypress', (event) => {
      const raw = input.value.trim();
      if (event.key !== 'Enter' || !wantsLocalSearch(raw)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      addBestLocal(raw).then((added) => {
        if (added) input.value = '';
      });
    }, true);

    if (addButton) {
      addButton.addEventListener('click', (event) => {
        const raw = input.value.trim();
        if (!wantsLocalSearch(raw)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        addBestLocal(raw).then((added) => {
          if (added) input.value = '';
        });
      }, true);
    }

    // Upper-case ticker input (AAPL, NVDA...) does not need a Yahoo info lookup just to autocomplete.
    input.addEventListener('input', (event) => {
      const raw = input.value.trim();
      if (!isTickerLike(raw) || wantsLocalSearch(raw)) return;
      event.stopImmediatePropagation();
      box.innerHTML = '';
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = '<span class="name">티커로 바로 추가</span><span class="symbol"></span>';
      item.querySelector('.symbol').textContent = raw;
      item.addEventListener('click', () => {
        if (typeof window.selectSearchResult === 'function') window.selectSearchResult(raw, raw);
      });
      box.appendChild(item);
      box.classList.remove('hidden');
    }, true);
  });
})();
