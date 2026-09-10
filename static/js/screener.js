(() => {
  'use strict';

  let payload = null;
  let loadingPromise = null;
  let preset = 'candidate';
  let market = 'ALL';
  let minValue = 1000000000; // 20일 평균 거래대금 10억원
  let sortKey = 'score';

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const num = (value, digits = 1) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits });
  };

  const pct = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    const n = Number(value);
    return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`;
  };

  const money = (value) => {
    if (!value) return '-';
    if (value >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
    if (value >= 1e8) return `${Math.round(value / 1e8).toLocaleString('ko-KR')}억`;
    return `${Math.round(value / 1e6).toLocaleString('ko-KR')}백만`;
  };

  function installTab() {
    const button = document.querySelector('[data-tab="ai"], [data-tab="screener"]');
    if (button) {
      button.dataset.tab = 'screener';
      button.textContent = '🔎 종목 발굴';
    }

    const tab = document.getElementById('screener-tab') || document.getElementById('ai-tab');
    if (!tab) return;
    tab.id = 'screener-tab';
    tab.innerHTML = `
      <section class="screener-section">
        <div class="screener-head">
          <div>
            <h2 class="screener-title">🔎 한국 주식 빠른 스크리너</h2>
            <p class="screener-desc">KOSPI·KOSDAQ 전체를 장 마감 후 미리 계산해 필터링은 즉시 실행됩니다.</p>
          </div>
          <div class="screener-update">무료 배치 계산 · 서버 실시간 전수조회 없음</div>
        </div>

        <div class="screener-controls">
          <div class="screener-row">
            <input id="screener-search" class="screener-search" placeholder="종목명 또는 6자리 코드 검색" autocomplete="off">
            <select id="screener-value" class="screen-select" aria-label="최소 평균 거래대금">
              <option value="0">거래대금 전체</option>
              <option value="1000000000" selected>평균 거래대금 10억+</option>
              <option value="5000000000">평균 거래대금 50억+</option>
              <option value="10000000000">평균 거래대금 100억+</option>
            </select>
            <select id="screener-sort" class="screen-select" aria-label="정렬 기준">
              <option value="score">기술점수 높은순</option>
              <option value="volumeRatio">거래량 급증순</option>
              <option value="rsi">RSI 낮은순</option>
              <option value="ret20">20일 수익률순</option>
              <option value="avgValue20">평균 거래대금순</option>
            </select>
          </div>

          <div class="screener-row">
            <button class="screen-chip active" data-screen-market="ALL">전체 시장</button>
            <button class="screen-chip" data-screen-market="KOSPI">KOSPI</button>
            <button class="screen-chip" data-screen-market="KOSDAQ">KOSDAQ</button>
          </div>

          <div class="screener-row">
            <button class="screen-chip active" data-screen-preset="candidate">종합 후보</button>
            <button class="screen-chip" data-screen-preset="oversold">RSI 과매도</button>
            <button class="screen-chip" data-screen-preset="volume">거래량 2배+</button>
            <button class="screen-chip" data-screen-preset="cross20">20일선 돌파</button>
            <button class="screen-chip" data-screen-preset="aligned">정배열</button>
            <button class="screen-chip" data-screen-preset="all">조건 없음</button>
          </div>
        </div>

        <div id="screener-summary" class="screener-summary">탭을 열면 최신 스크리너 데이터를 불러옵니다.</div>
        <div id="screener-results"><div class="screener-empty">종목 발굴 탭을 열어주세요.</div></div>
        <div class="screener-note">기술점수는 RSI·이평선·거래량을 조합한 탐색용 지표이며 투자판단 점수가 아닙니다. 데이터는 한국 장 마감 후 자동 갱신됩니다.</div>
      </section>`;
  }

  function matches(row) {
    if (market !== 'ALL' && row.market !== market) return false;
    if ((row.avgValue20 || 0) < minValue) return false;

    const query = (document.getElementById('screener-search')?.value || '').trim().toLowerCase();
    if (query && !`${row.name} ${row.code} ${row.symbol}`.toLowerCase().includes(query)) return false;

    if (preset === 'oversold') return row.rsi14 !== null && row.rsi14 <= 35;
    if (preset === 'volume') return (row.volumeRatio || 0) >= 2;
    if (preset === 'cross20') return row.cross20 === true;
    if (preset === 'aligned') return row.aligned === true;
    if (preset === 'candidate') {
      return (row.score || 0) >= 55 && (row.rsi14 === null || row.rsi14 <= 65) && (row.volumeRatio || 0) >= 1.2;
    }
    return true;
  }

  function sortRows(rows) {
    const result = [...rows];
    const desc = (key) => result.sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity));
    if (sortKey === 'volumeRatio') return desc('volumeRatio');
    if (sortKey === 'ret20') return desc('ret20');
    if (sortKey === 'avgValue20') return desc('avgValue20');
    if (sortKey === 'rsi') return result.sort((a, b) => (a.rsi14 ?? Infinity) - (b.rsi14 ?? Infinity));
    return desc('score');
  }

  function trendBadge(row) {
    if (row.aligned) return '<span class="screen-badge good">정배열</span>';
    if (row.cross20) return '<span class="screen-badge cross">20일선 돌파</span>';
    if (row.above20 && row.above60) return '<span class="screen-badge">20·60일선 위</span>';
    if (row.above20) return '<span class="screen-badge">20일선 위</span>';
    return '<span class="screen-badge muted">이평선 아래</span>';
  }

  function render() {
    if (!payload) return;
    const results = document.getElementById('screener-results');
    const summary = document.getElementById('screener-summary');
    if (!results || !summary) return;

    let rows = sortRows(payload.stocks.filter(matches));
    const total = rows.length;
    rows = rows.slice(0, 200);

    summary.textContent = `${total.toLocaleString('ko-KR')}개 종목 · ${payload.tradeDate || '-'} 기준 · 전체 ${payload.count?.toLocaleString('ko-KR') || '-'}개에서 즉시 필터링`;

    if (!rows.length) {
      results.innerHTML = '<div class="screener-empty">조건에 맞는 종목이 없습니다. 필터를 완화해 보세요.</div>';
      return;
    }

    results.innerHTML = `<div class="screener-table-wrap"><table class="screener-table">
      <thead><tr><th>종목</th><th>현재가</th><th>RSI</th><th>거래량</th><th>추세</th><th>20일</th><th>평균 거래대금</th><th>점수</th><th></th></tr></thead>
      <tbody>${rows.map((row) => `
        <tr>
          <td><div class="screen-name">${esc(row.name)}</div><div class="screen-code">${esc(row.code)} · ${esc(row.market)}</div></td>
          <td><div>${num(row.price, 0)}원</div><div class="${(row.change1d || 0) >= 0 ? 'screen-up' : 'screen-down'}">${pct(row.change1d)}</div></td>
          <td><strong>${num(row.rsi14, 1)}</strong></td>
          <td><strong>${row.volumeRatio ? `${Number(row.volumeRatio).toFixed(1)}x` : '-'}</strong></td>
          <td>${trendBadge(row)}</td>
          <td class="${(row.ret20 || 0) >= 0 ? 'screen-up' : 'screen-down'}">${pct(row.ret20)}</td>
          <td><strong>${money(row.avgValue20)}</strong><div class="screen-sub">5일 ${pct(row.ret5)} · 60일 ${pct(row.ret60)}</div></td>
          <td><span class="screen-score">${num(row.score, 0)}</span></td>
          <td><button class="screen-add" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">비교+</button></td>
        </tr>`).join('')}</tbody></table></div>`;

    results.querySelectorAll('.screen-add').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.symbol;
        const name = button.dataset.name;
        if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
        if (typeof window.switchTab === 'function') window.switchTab('chart');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  async function loadData() {
    if (payload) {
      render();
      return payload;
    }
    if (loadingPromise) return loadingPromise;

    const results = document.getElementById('screener-results');
    if (results) results.innerHTML = '<div class="screener-loading"><div class="spinner"></div><span>스크리너 데이터를 불러오는 중...</span></div>';

    loadingPromise = fetch('/static/data/screener.json', { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => {
        payload = data;
        render();
        return data;
      })
      .catch((error) => {
        console.error('Screener load failed:', error);
        if (results) results.innerHTML = '<div class="screener-empty">첫 스크리너 데이터를 생성 중입니다. 잠시 후 새로고침해 주세요.</div>';
        throw error;
      })
      .finally(() => { loadingPromise = null; });

    return loadingPromise;
  }

  function bind() {
    document.querySelector('[data-tab="screener"]')?.addEventListener('click', () => loadData().catch(() => {}));

    document.querySelectorAll('[data-screen-preset]').forEach((button) => {
      button.addEventListener('click', () => {
        document.querySelectorAll('[data-screen-preset]').forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
        preset = button.dataset.screenPreset;
        render();
      });
    });

    document.querySelectorAll('[data-screen-market]').forEach((button) => {
      button.addEventListener('click', () => {
        document.querySelectorAll('[data-screen-market]').forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
        market = button.dataset.screenMarket;
        render();
      });
    });

    document.getElementById('screener-search')?.addEventListener('input', render);
    document.getElementById('screener-value')?.addEventListener('change', (event) => {
      minValue = Number(event.target.value);
      render();
    });
    document.getElementById('screener-sort')?.addEventListener('change', (event) => {
      sortKey = event.target.value;
      render();
    });
  }

  function init() {
    installTab();
    bind();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
