(() => {
  'use strict';

  if (window.__chartViewReleaseUiV40) return;
  window.__chartViewReleaseUiV40 = true;

  const basisCache = new Map();
  const basisInflight = new Map();
  let homeObserver = null;
  let valuationObserver = null;
  let screenerObserver = null;
  let macroObserver = null;

  function storageWarning(detail) {
    let banner = document.getElementById('v40-storage-warning');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'v40-storage-warning';
      banner.className = 'v40-storage-warning';
      banner.setAttribute('role', 'alert');
      document.body.appendChild(banner);
    }
    banner.innerHTML = '<strong>이 기기에 변경 내용을 저장하지 못했습니다.</strong><span>현재 화면에는 반영될 수 있지만 새로고침 후 유지되지 않을 수 있습니다. 저장 공간·브라우저 설정을 확인해 주세요.</span>';
    banner.hidden = false;
    console.warn('[storage v40]', detail || 'write failed');
  }

  function installStorageWarning() {
    document.addEventListener('chartview:storage-error', (event) => storageWarning(event.detail));
  }

  function syncTabAccessibility() {
    document.querySelectorAll('.tab-content').forEach((tab) => {
      const active = tab.classList.contains('active') && !tab.hidden;
      tab.setAttribute('aria-hidden', String(!active));
      if ('inert' in tab) tab.inert = !active;
    });
  }

  function installSearchKeyboard() {
    const apply = () => {
      const box = document.getElementById('search-results');
      if (!box) return;
      box.setAttribute('role', 'listbox');
      box.querySelectorAll('.search-result-item').forEach((item) => {
        if (item.dataset.v40Keyboard === '1') return;
        item.dataset.v40Keyboard = '1';
        item.setAttribute('role', 'option');
        item.tabIndex = 0;
        item.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); item.click(); }
        });
      });
    };
    const box = document.getElementById('search-results');
    if (box) new MutationObserver(apply).observe(box, { childList: true });
    apply();
  }

  const shortDate = (raw) => {
    const m = String(raw || '').match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[2]}.${m[3]}` : '';
  };

  async function fetchBasis(symbols) {
    const missing = symbols.filter((symbol) => symbol && !basisCache.has(symbol));
    for (let i = 0; i < missing.length; i += 6) {
      const chunk = missing.slice(i, i + 6);
      const key = chunk.join(',');
      if (basisInflight.has(key)) { await basisInflight.get(key); continue; }
      const job = fetch(`/api/compare?tickers=${encodeURIComponent(key)}&period=1mo`, { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : null)
        .then((payload) => {
          (payload?.stocks || []).forEach((stock) => {
            const symbol = String(stock.ticker || '').toUpperCase();
            const end = stock.actualEnd || stock.endDate || stock?.meta?.actualEnd || stock?.meta?.end || stock.asOf || '';
            if (symbol) basisCache.set(symbol, end);
          });
        }).catch(() => {}).finally(() => basisInflight.delete(key));
      basisInflight.set(key, job);
      await job;
    }
  }

  async function decorateHomeWatchlist() {
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return;
    const buttons = [...section.querySelectorAll('[data-home-watch-open]')];
    const symbols = buttons.map((button) => String(button.dataset.homeWatchOpen || '').toUpperCase()).filter(Boolean);
    await fetchBasis(symbols);
    buttons.forEach((button) => {
      const symbol = String(button.dataset.homeWatchOpen || '').toUpperCase();
      let basis = button.querySelector('.home-watch-v40-basis');
      if (!basis) {
        basis = document.createElement('span');
        basis.className = 'home-watch-v40-basis';
        button.appendChild(basis);
      }
      const text = `${shortDate(basisCache.get(symbol)) || '기준 확인'} 거래 · 1달`;
      if (basis.textContent !== text) basis.textContent = text;
    });
  }

  function observeHomeWatchlist() {
    const attach = () => {
      const section = document.getElementById('home-watchlist-v30');
      if (!section) return false;
      if (!homeObserver) {
        let scheduled = false;
        homeObserver = new MutationObserver(() => {
          if (scheduled) return;
          scheduled = true;
          requestAnimationFrame(() => { scheduled = false; decorateHomeWatchlist().catch(() => {}); });
        });
        homeObserver.observe(section, { childList: true, subtree: true });
      }
      decorateHomeWatchlist().catch(() => {});
      return true;
    };
    if (!attach()) {
      let tries = 0;
      const timer = setInterval(() => { if (attach() || ++tries > 40) clearInterval(timer); }, 250);
    }
  }

  function installMarketMore() {
    const panel = document.getElementById('home-market-v9');
    if (!panel || panel.querySelector('[data-v40-market-more]')) return false;
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.v40MarketMore = '1';
    button.className = 'v40-market-more';
    button.textContent = '나머지 시장 지표 보기';
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', () => {
      const expanded = panel.classList.toggle('v40-market-expanded');
      button.setAttribute('aria-expanded', String(expanded));
      button.textContent = expanded ? '시장 지표 접기' : '나머지 시장 지표 보기';
    });
    panel.appendChild(button);
    return true;
  }

  function patchValuationConfig() {
    try {
      if (typeof METRIC_CONFIG === 'undefined' || !METRIC_CONFIG.overview) return false;
      const config = METRIC_CONFIG.overview;
      if (!config.__v40) {
        config.columns = [
          { key: 'forwardPE', label: 'FWD PER', format: 'number', color: true },
          { key: 'trailingPE', label: 'PER', format: 'number', color: true },
          { key: 'roe', label: 'ROE(%)', format: 'percent', color: true },
        ];
        config.sortKey = 'forwardPE';
        config.barKey = 'forwardPE';
        config.barLabel = 'FWD PER · 예상 기간 미확인';
        config.title = '핵심 밸류에이션 비교';
        config.description = '현재가와 FWD PER·PER·ROE를 먼저 비교합니다. FWD PER의 예상 기간은 제공처에서 확인되지 않은 경우 추정하지 않습니다.';
        config.__v40 = true;
      }
      if (typeof currentMetric !== 'undefined' && currentMetric === 'overview' && typeof renderPerTable === 'function') renderPerTable();
      return true;
    } catch (_) { return false; }
  }

  function syncValuationSortLabels() {
    try {
      const config = typeof METRIC_CONFIG !== 'undefined' ? (METRIC_CONFIG[currentMetric] || METRIC_CONFIG.overview) : null;
      const label = config?.columns?.find((c) => c.key === config.sortKey)?.label || config?.barLabel || '지표';
      const asc = document.querySelector('.sort-btn[data-sort="metric-asc"]');
      const desc = document.querySelector('.sort-btn[data-sort="metric-desc"]');
      if (asc) asc.textContent = `${label.replace(/\s*·.*$/, '')} 낮은순`;
      if (desc) desc.textContent = `${label.replace(/\s*·.*$/, '')} 높은순`;
    } catch (_) { }
  }

  function installMetricPicker() {
    const section = document.querySelector('#fwdper-tab .metric-section');
    if (!section || section.querySelector('.v40-metric-picker')) return;
    const details = document.createElement('details');
    details.className = 'v40-metric-picker';
    details.innerHTML = `<summary>지표 선택 · 전체 지표 보기</summary><div>${[
      ['overview','핵심 비교'],['fwd_per','FWD PER'],['trailing_pe','PER'],['pbr','PBR'],['psr','PSR'],['ev','EV/EBITDA'],['dividend','배당률'],['profitability','ROE']
    ].map(([key,label]) => `<button type="button" data-v40-metric="${key}">${label}</button>`).join('')}</div>`;
    section.appendChild(details);
    details.querySelectorAll('[data-v40-metric]').forEach((button) => button.addEventListener('click', () => {
      try {
        currentMetric = button.dataset.v40Metric;
        currentSort = 'default';
        document.querySelectorAll('.sort-btn').forEach((el) => el.classList.toggle('active', el.dataset.sort === 'default'));
        if (typeof renderPerTable === 'function') renderPerTable();
        syncValuationSortLabels();
        details.open = false;
      } catch (_) { }
    }));
  }

  function addBasisControls() {
    const container = document.getElementById('per-table-container');
    if (!container) return;
    container.querySelectorAll('td').forEach((cell) => {
      if (cell.querySelector('.v40-cell-basis')) return;
      const meta = cell.querySelector('.metric-provenance');
      const text = meta?.textContent?.trim() || cell.dataset.provenance || cell.title || '';
      if (!text) return;
      const details = document.createElement('details');
      details.className = 'v40-cell-basis';
      details.innerHTML = `<summary>기준 보기</summary><p>${text.replaceAll('<','&lt;').replaceAll('>','&gt;')}</p>`;
      cell.appendChild(details);
    });
    syncValuationSortLabels();
  }

  function observeValuation() {
    const attach = () => {
      const container = document.getElementById('per-table-container');
      if (!container) return false;
      patchValuationConfig();
      installMetricPicker();
      addBasisControls();
      if (!valuationObserver) {
        let pending = false;
        valuationObserver = new MutationObserver(() => {
          if (pending) return;
          pending = true;
          requestAnimationFrame(() => { pending = false; addBasisControls(); });
        });
        valuationObserver.observe(container, { childList: true, subtree: true });
      }
      return true;
    };
    if (!attach()) setTimeout(observeValuation, 400);
  }

  function screenerConditionText() {
    const search = document.getElementById('screener-search')?.value?.trim();
    const value = document.getElementById('screener-value')?.selectedOptions?.[0]?.textContent;
    const sort = document.getElementById('screener-sort')?.selectedOptions?.[0]?.textContent;
    const market = document.querySelector('[data-screen-market].active')?.textContent?.trim();
    const preset = document.querySelector('[data-screen-preset].active')?.textContent?.trim();
    return [market, preset, value, sort, search ? `검색: ${search}` : ''].filter(Boolean).join(' · ');
  }

  function updateScreenerConditionBar() {
    const bar = document.querySelector('.v40-screener-conditions');
    const text = bar?.querySelector('[data-v40-condition-text]');
    if (text) text.textContent = screenerConditionText() || '적용 조건 없음';
  }

  function installScreenerConditionBar() {
    const controls = document.querySelector('#screener-tab .screener-controls');
    if (!controls || document.querySelector('.v40-screener-conditions')) return false;
    const bar = document.createElement('div');
    bar.className = 'v40-screener-conditions';
    bar.innerHTML = '<div><span>적용 조건</span><strong data-v40-condition-text></strong></div><button type="button" data-v40-reset>조건 초기화</button>';
    controls.insertAdjacentElement('afterend', bar);
    bar.querySelector('[data-v40-reset]')?.addEventListener('click', () => {
      const search = document.getElementById('screener-search');
      const value = document.getElementById('screener-value');
      const sort = document.getElementById('screener-sort');
      if (search) { search.value = ''; search.dispatchEvent(new Event('input', { bubbles: true })); }
      if (value) { value.value = '1000000000'; value.dispatchEvent(new Event('change', { bubbles: true })); }
      if (sort) { sort.value = 'score'; sort.dispatchEvent(new Event('change', { bubbles: true })); }
      document.querySelector('[data-screen-market="ALL"]')?.click();
      document.querySelector('[data-screen-preset="candidate"]')?.click();
      updateScreenerConditionBar();
    });
    controls.addEventListener('input', updateScreenerConditionBar);
    controls.addEventListener('change', updateScreenerConditionBar);
    controls.addEventListener('click', () => setTimeout(updateScreenerConditionBar, 0));
    updateScreenerConditionBar();
    return true;
  }

  function polishScreenerResults() {
    const root = document.getElementById('screener-results');
    if (!root) return;
    root.querySelectorAll('.screen-add').forEach((button) => { button.textContent = '비교에 추가'; button.setAttribute('aria-label', `${button.dataset.name || button.dataset.symbol} 비교에 추가`); });
    root.querySelectorAll('.screen-idea').forEach((button) => { button.textContent = '상세 보기'; button.setAttribute('aria-label', `${button.dataset.name || button.dataset.symbol} 상세 보기`); });
    const table = root.querySelector('.screener-table');
    if (!table || table.dataset.v40Polished === '1') return;
    table.dataset.v40Polished = '1';
    const headers = [...table.querySelectorAll('thead th')];
    const perfHeader = headers.find((th) => th.textContent.trim() === '20일');
    if (perfHeader) perfHeader.textContent = '성과';
    table.querySelectorAll('tbody tr').forEach((row) => {
      const perf = row.querySelector('td[data-label="20일"]');
      const avg = row.querySelector('td[data-label="평균 거래대금"]');
      const extra = avg?.querySelector('.screen-sub');
      if (perf) {
        perf.dataset.label = '성과';
        if (extra) {
          const more = document.createElement('div');
          more.className = 'v40-performance-more';
          more.textContent = extra.textContent || '';
          perf.appendChild(more);
          extra.remove();
        }
      }
    });
  }

  function observeScreener() {
    if (!installScreenerConditionBar()) setTimeout(installScreenerConditionBar, 400);
    const root = document.getElementById('screener-results');
    if (!root) { setTimeout(observeScreener, 400); return; }
    polishScreenerResults();
    if (!screenerObserver) {
      let pending = false;
      screenerObserver = new MutationObserver(() => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => { pending = false; polishScreenerResults(); });
      });
      screenerObserver.observe(root, { childList: true, subtree: true });
    }
  }

  function macroCategory(symbol) {
    if (/T10Y|FEDFUNDS|DFII10|T10YIE/.test(symbol)) return '금리';
    if (/VIX|BAML/.test(symbol)) return '위험';
    if (/WALCL|TGA|RRP|M2SL|WTREGEN/.test(symbol)) return '유동성';
    return '경기';
  }

  function polishMacro() {
    const freshness = document.getElementById('macro-freshness');
    if (freshness) {
      freshness.querySelectorAll('span').forEach((node) => {
        if (/fresh\s+\d+\s+·\s+stale\s+\d+/i.test(node.textContent || '')) {
          const m = (node.textContent || '').match(/fresh\s+(\d+)\s+·\s+stale\s+(\d+)/i);
          if (m) node.textContent = `정상 수집 ${m[1]}개 · 이전값 ${m[2]}개`;
        }
      });
    }
    document.querySelectorAll('.stale-badge').forEach((badge) => { badge.textContent = '이전값'; });
    const grid = document.getElementById('macro-grid');
    if (!grid || grid.querySelector('.v40-macro-groups')) return;
    const cards = [...grid.children].filter((node) => node.classList?.contains('macro-card'));
    if (cards.length < 4) return;
    const wrap = document.createElement('div');
    wrap.className = 'v40-macro-groups';
    const buckets = new Map(['금리','위험','유동성','경기'].map((name) => [name, []]));
    cards.forEach((card) => {
      const symbol = card.querySelector('.mc-symbol')?.textContent || '';
      buckets.get(macroCategory(symbol))?.push(card);
    });
    buckets.forEach((rows, name) => {
      if (!rows.length) return;
      const group = document.createElement('section');
      group.className = 'v40-macro-group';
      group.innerHTML = `<h3>${name}</h3><div></div>`;
      rows.forEach((card) => group.lastElementChild.appendChild(card));
      wrap.appendChild(group);
    });
    grid.appendChild(wrap);
  }

  function observeMacro() {
    const section = document.querySelector('.macro-section');
    if (!section) { setTimeout(observeMacro, 500); return; }
    polishMacro();
    if (!macroObserver) {
      let pending = false;
      macroObserver = new MutationObserver(() => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => { pending = false; polishMacro(); });
      });
      macroObserver.observe(section, { childList: true, subtree: true });
    }
  }

  function installGlobalInteractions() {
    document.addEventListener('click', () => setTimeout(syncTabAccessibility, 0));
    window.addEventListener('popstate', () => setTimeout(syncTabAccessibility, 0));
    document.querySelectorAll('.sort-btn, .metric-chip').forEach((button) => button.addEventListener('click', () => setTimeout(syncValuationSortLabels, 0)));
  }

  function init() {
    installStorageWarning();
    installSearchKeyboard();
    observeHomeWatchlist();
    installMarketMore();
    observeValuation();
    observeScreener();
    observeMacro();
    installGlobalInteractions();
    syncTabAccessibility();
    setTimeout(installMarketMore, 700);
    setTimeout(syncTabAccessibility, 1200);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
