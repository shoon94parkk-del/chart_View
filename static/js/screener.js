(() => {
  'use strict';

  let payload = null;
  let loadingPromise = null;
  let preset = 'all';
  let market = 'ALL';
  let minValue = 0;
  let sortKey = 'score';
  let quickFilter = 'none';
  const SCORE_MAX = 30;
  const CANDIDATE_SCORE_MIN = 22;
  const customFilters = { rsiMin: null, rsiMax: null, volumeMin: null, ret20Min: null, scoreMin: null, trend: 'any' };

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
          <div class="screener-update">장마감 배치 · 서버 실시간 전수조회 없음</div>
        </div>

        <div class="screener-controls">
          <div class="screener-row screener-main-row">
            <input id="screener-search" class="screener-search" placeholder="종목명 또는 6자리 코드 검색" autocomplete="off">
            <select id="screener-value" class="screen-select" aria-label="최소 평균 거래대금">
              <option value="0" selected>거래대금 전체</option>
              <option value="1000000000">평균 거래대금 10억+</option>
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

          <div class="screener-row screen-scroll-row">
            <button class="screen-chip active" data-screen-market="ALL">전체 시장</button>
            <button class="screen-chip" data-screen-market="KOSPI">KOSPI</button>
            <button class="screen-chip" data-screen-market="KOSDAQ">KOSDAQ</button>
          </div>

          <div class="screener-row screen-scroll-row">
            <button class="screen-chip" data-screen-preset="candidate"><span>종합 후보</span><small data-screen-preset-count>…</small></button>
            <button class="screen-chip" data-screen-preset="momentum"><span>추세+거래량</span><small data-screen-preset-count>…</small></button>
            <button class="screen-chip" data-screen-preset="oversold"><span>RSI 과매도</span><small data-screen-preset-count>…</small></button>
            <button class="screen-chip" data-screen-preset="volume"><span>거래량 2배+</span><small data-screen-preset-count>…</small></button>
            <button class="screen-chip" data-screen-preset="cross20"><span>20일선 돌파</span><small data-screen-preset-count>…</small></button>
            <button class="screen-chip" data-screen-preset="aligned"><span>정배열</span><small data-screen-preset-count>…</small></button>
            <button class="screen-chip active" data-screen-preset="all"><span>전체 보기</span><small data-screen-preset-count>…</small></button>
          </div>

          <details class="screener-custom-filters">
            <summary>직접 조건 설정 <span><b data-screen-custom-count>0</b>개 적용</span></summary>
            <div class="screener-custom-grid">
              <label><span>RSI 최소</span><input type="number" inputmode="decimal" min="0" max="100" step="1" placeholder="예: 30" data-screen-custom="rsiMin"></label>
              <label><span>RSI 최대</span><input type="number" inputmode="decimal" min="0" max="100" step="1" placeholder="예: 60" data-screen-custom="rsiMax"></label>
              <label><span>거래량 배수 이상</span><input type="number" inputmode="decimal" min="0" step="0.1" placeholder="예: 1.5" data-screen-custom="volumeMin"></label>
              <label><span>20일 수익률 이상</span><input type="number" inputmode="decimal" step="1" placeholder="예: -5" data-screen-custom="ret20Min"></label>
              <label><span>기술점수 이상 (30점 만점)</span><input type="number" inputmode="numeric" min="0" max="30" step="1" placeholder="예: 18" data-screen-custom="scoreMin"></label>
              <label><span>추세 상태</span><select data-screen-custom="trend"><option value="any">전체</option><option value="above20">20일선 위</option><option value="cross20">20일선 돌파</option><option value="aligned">정배열</option></select></label>
              <button type="button" class="screener-custom-reset" data-screen-custom-reset>직접 조건 지우기</button>
            </div>
          </details>
        </div>

        <div id="screener-summary" class="screener-summary">탭을 열면 최신 스크리너 데이터를 불러옵니다.</div>
        <div id="screener-results"><div class="screener-empty">종목 발굴 탭을 열어주세요.</div></div>
        <div class="screener-note">기술점수는 RSI·이평선·거래량을 조합한 30점 만점 탐색용 지표이며 투자판단 점수가 아닙니다. 종합 후보는 기술점수 ${CANDIDATE_SCORE_MIN}점 이상에 거래량·과열 조건을 함께 적용합니다. 종목별 실적·밸류에이션은 투자 아이디어 탭에서 별도로 확인하세요.</div>
      </section>`;
  }

  function matchesBase(row) {
    if (market !== 'ALL' && row.market !== market) return false;
    if ((row.avgValue20 || 0) < minValue) return false;

    if (quickFilter === 'up' && !((row.change1d || 0) > 0)) return false;
    if (quickFilter === 'rsi35' && !(row.rsi14 !== null && row.rsi14 !== undefined && Number(row.rsi14) <= 35)) return false;
    if (quickFilter === 'volume2x' && !((row.volumeRatio || 0) >= 2)) return false;

    const rsi = row.rsi14 == null ? null : Number(row.rsi14);
    if (customFilters.rsiMin != null && !(rsi != null && rsi >= customFilters.rsiMin)) return false;
    if (customFilters.rsiMax != null && !(rsi != null && rsi <= customFilters.rsiMax)) return false;
    if (customFilters.volumeMin != null && Number(row.volumeRatio || 0) < customFilters.volumeMin) return false;
    if (customFilters.ret20Min != null && Number(row.ret20 ?? -Infinity) < customFilters.ret20Min) return false;
    if (customFilters.scoreMin != null && Number(row.score || 0) < customFilters.scoreMin) return false;
    if (customFilters.trend === 'above20' && row.above20 !== true) return false;
    if (customFilters.trend === 'cross20' && row.cross20 !== true) return false;
    if (customFilters.trend === 'aligned' && row.aligned !== true) return false;

    const query = (document.getElementById('screener-search')?.value || '').trim().toLowerCase();
    if (query && !`${row.name} ${row.code} ${row.symbol}`.toLowerCase().includes(query)) return false;

    return true;
  }

  function matchesPreset(row, targetPreset = preset) {
    if (targetPreset === 'oversold') return row.rsi14 !== null && row.rsi14 <= 35;
    if (targetPreset === 'volume') return (row.volumeRatio || 0) >= 2;
    if (targetPreset === 'cross20') return row.cross20 === true;
    if (targetPreset === 'aligned') return row.aligned === true;
    if (targetPreset === 'momentum') return (row.volumeRatio || 0) >= 1.5 && (row.aligned === true || row.cross20 === true) && (row.rsi14 == null || row.rsi14 < 70);
    if (targetPreset === 'candidate') {
      return (row.score || 0) >= CANDIDATE_SCORE_MIN && (row.rsi14 === null || row.rsi14 <= 65) && (row.volumeRatio || 0) >= 1.2;
    }
    return true;
  }

  function matches(row) {
    return matchesBase(row) && matchesPreset(row);
  }

  function updatePresetCounts() {
    if (!payload?.stocks) return;
    document.querySelectorAll('[data-screen-preset]').forEach((button) => {
      const count = payload.stocks.filter((row) => matchesBase(row) && matchesPreset(row, button.dataset.screenPreset)).length;
      const badge = button.querySelector('[data-screen-preset-count]');
      if (badge) badge.textContent = count.toLocaleString('ko-KR');
      button.setAttribute('aria-label', `${button.querySelector('span')?.textContent || ''} ${count.toLocaleString('ko-KR')}개`);
    });
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

    updatePresetCounts();
    let rows = sortRows(payload.stocks.filter(matches));
    const total = rows.length;
    const shown = Math.min(total, 200);
    rows = rows.slice(0, 200);

    const quickLabel = ({ up: '상승 종목만', rsi35: 'RSI 35↓', volume2x: '거래량 2x+' })[quickFilter];
    summary.textContent = `${total.toLocaleString('ko-KR')}개 조건 일치 · ${payload.tradeDate || '-'} 기준 · ${shown.toLocaleString('ko-KR')}개 표시${total > 200 ? ' (상위 200)' : ''}${quickLabel ? ` · ${quickLabel}` : ''}`;

    if (!rows.length) {
      results.innerHTML = '<div class="screener-empty">조건에 맞는 종목이 없습니다. 필터를 완화해 보세요.</div>';
      return;
    }

    results.innerHTML = `<div class="screener-table-wrap"><table class="screener-table">
      <thead><tr><th>종목</th><th>현재가</th><th>RSI</th><th>거래량</th><th>추세</th><th>20일</th><th>평균 거래대금</th><th>점수 /${SCORE_MAX}</th><th>액션</th></tr></thead>
      <tbody>${rows.map((row) => `
        <tr>
          <td data-label="종목"><div class="screen-name">${esc(row.name)}</div><div class="screen-code">${esc(row.code)} · ${esc(row.market)}</div></td>
          <td data-label="현재가"><div>${num(row.price, 0)}원</div><div class="${(row.change1d || 0) >= 0 ? 'screen-up' : 'screen-down'}">${pct(row.change1d)}</div></td>
          <td data-label="RSI"><strong>${num(row.rsi14, 1)}</strong></td>
          <td data-label="거래량"><strong>${row.volumeRatio ? `${Number(row.volumeRatio).toFixed(1)}x` : '-'}</strong></td>
          <td data-label="추세">${trendBadge(row)}</td>
          <td data-label="20일" class="${(row.ret20 || 0) >= 0 ? 'screen-up' : 'screen-down'}">${pct(row.ret20)}</td>
          <td data-label="평균 거래대금"><strong>${money(row.avgValue20)}</strong><div class="screen-sub">5일 ${pct(row.ret5)} · 60일 ${pct(row.ret60)}</div></td>
          <td data-label="기술점수"><span class="screen-score">${num(row.score, 0)}</span></td>
          <td data-label="액션"><div class="screen-actions"><button class="screen-add" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">비교+</button><button class="screen-idea" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">아이디어</button><button class="screen-watch ${typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(row.symbol) ? 'active' : ''}" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}" aria-label="${esc(row.name)} 관심종목">${typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(row.symbol) ? '★' : '☆'}</button></div></td>
        </tr>`).join('')}</tbody></table></div>`;

    results.querySelectorAll('.screen-add').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.symbol;
        const name = button.dataset.name;
        if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
        if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
        else if (typeof window.switchTab === 'function') window.switchTab('chart');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    results.querySelectorAll('.screen-watch').forEach((button) => {
      button.addEventListener('click', () => {
        if (typeof window.__toggleWatchlist !== 'function') return;
        window.__toggleWatchlist(button.dataset.symbol, button.dataset.name);
        const active = typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(button.dataset.symbol);
        button.classList.toggle('active', active);
        button.textContent = active ? '★' : '☆';
      });
    });

    results.querySelectorAll('.screen-idea').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.symbol;
        const name = button.dataset.name;
        if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
        if (typeof window.__openAppTab === 'function') window.__openAppTab('ideas');
        else { const ideasTab = document.querySelector('[data-tab="ideas"]'); if (ideasTab) ideasTab.click(); else if (typeof window.switchTab === 'function') window.switchTab('fwdper'); }
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  async function screenerDataUrl() {
    try {
      const response = await fetch('/static/data/screener_meta.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`meta HTTP ${response.status}`);
      const meta = await response.json();
      const version = meta.tradeDate || meta.updated || 'latest';
      return `/static/data/screener.json?v=${encodeURIComponent(version)}`;
    } catch (_) {
      return `/static/data/screener.json?v=${Date.now()}`;
    }
  }

  async function loadData() {
    if (payload) {
      render();
      return payload;
    }
    if (loadingPromise) return loadingPromise;

    const results = document.getElementById('screener-results');
    if (results) results.innerHTML = '<div class="screener-loading"><div class="spinner"></div><span>스크리너 데이터를 불러오는 중...</span></div>';

    loadingPromise = screenerDataUrl()
      .then((url) => fetch(url, { cache: 'force-cache' }))
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
        if (results) results.innerHTML = '<div class="screener-empty">스크리너 데이터를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.</div>';
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

    const readCustomFilters = () => {
      document.querySelectorAll('[data-screen-custom]').forEach((control) => {
        const key = control.dataset.screenCustom;
        customFilters[key] = key === 'trend' ? control.value : (control.value === '' ? null : Number(control.value));
      });
      const count = Object.entries(customFilters).filter(([key, value]) => key === 'trend' ? value !== 'any' : value != null).length;
      const countNode = document.querySelector('[data-screen-custom-count]');
      if (countNode) countNode.textContent = String(count);
      document.dispatchEvent(new CustomEvent('screener:customfilter', { detail: { count } }));
    };
    document.querySelectorAll('[data-screen-custom]').forEach((control) => {
      control.addEventListener(control.tagName === 'SELECT' ? 'change' : 'input', () => {
        readCustomFilters();
        preset = 'all';
        document.querySelectorAll('[data-screen-preset]').forEach((item) => item.classList.toggle('active', item.dataset.screenPreset === 'all'));
        render();
      });
    });
    window.__resetScreenerCustomFilters = function () {
      document.querySelectorAll('[data-screen-custom]').forEach((control) => { control.value = control.dataset.screenCustom === 'trend' ? 'any' : ''; });
      readCustomFilters();
      render();
    };
    window.__getScreenerCustomFilters = function () { return { ...customFilters }; };
    document.querySelector('[data-screen-custom-reset]')?.addEventListener('click', window.__resetScreenerCustomFilters);
  }

  window.__setScreenerQuickFilter = function (value = 'none') {
    const allowed = new Set(['none', 'up', 'rsi35', 'volume2x']);
    quickFilter = allowed.has(value) ? value : 'none';
    render();
    document.dispatchEvent(new CustomEvent('screener:quickfilter', { detail: { value: quickFilter } }));
    return quickFilter;
  };

  window.__getScreenerQuickFilter = function () { return quickFilter; };

  function init() {
    installTab();
    bind();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
