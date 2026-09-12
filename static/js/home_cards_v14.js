(() => {
  'use strict';

  let sourcePromise = null;
  let renderBusy = false;
  let renderQueued = false;

  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const num = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const pct = (value, digits = 1) => {
    const n = num(value);
    return n === null ? '-' : `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
  };
  const revisionPct = (current, previous) => {
    const a = num(current), b = num(previous);
    if (a === null || b === null || a <= 0 || b <= 0) return null;
    return (a / b - 1) * 100;
  };

  const LOGO_DOMAINS = {
    AAPL: 'apple.com', NVDA: 'nvidia.com', MSFT: 'microsoft.com', GOOGL: 'google.com', GOOG: 'google.com',
    META: 'meta.com', AMZN: 'amazon.com', TSLA: 'tesla.com', AMD: 'amd.com', AVGO: 'broadcom.com', TSM: 'tsmc.com',
    MU: 'micron.com', INTC: 'intel.com', QCOM: 'qualcomm.com', NFLX: 'netflix.com', JPM: 'jpmorganchase.com',
    BAC: 'bankofamerica.com', GS: 'goldmansachs.com', V: 'visa.com', MA: 'mastercard.com', LLY: 'lilly.com',
    ABBV: 'abbvie.com', JNJ: 'jnj.com', PFE: 'pfizer.com', UNH: 'unitedhealthgroup.com', XOM: 'exxonmobil.com', CVX: 'chevron.com',
    '005930.KS': 'samsung.com', '000660.KS': 'skhynix.com', '006400.KS': 'samsungsdi.com', '035420.KS': 'navercorp.com',
    '035720.KS': 'kakaocorp.com', '051910.KS': 'lgchem.com', '005380.KS': 'hyundai.com', '000270.KS': 'kia.com',
    '068270.KS': 'celltrion.com', '207940.KS': 'samsungbiologics.com', '373220.KS': 'lgensol.com', '066570.KS': 'lg.com',
    '009150.KS': 'samsungsem.com', '018260.KS': 'samsungsds.com', '028260.KS': 'samsungcnt.com'
  };

  function initials(name, symbol) {
    const source = String(name || symbol || '?').replace(/[^0-9A-Za-z가-힣]/g, '');
    return esc(source.slice(0, 2).toUpperCase() || '?');
  }

  function logoMarkup(symbol, name, variant = 'round') {
    const domain = LOGO_DOMAINS[symbol];
    const fallback = `<span class="home14-logo-fallback">${initials(name, symbol)}</span>`;
    if (!domain) return `<span class="home14-logo ${variant}">${fallback}</span>`;
    const src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`;
    return `<span class="home14-logo ${variant}"><img src="${src}" alt="" loading="lazy" decoding="async" data-home14-logo>${fallback}</span>`;
  }

  function selectedTickersNow() {
    try {
      if (typeof selectedTickers !== 'undefined' && Array.isArray(selectedTickers) && selectedTickers.length) return [...selectedTickers];
    } catch (_) {}
    try {
      if (typeof perTickers !== 'undefined' && Array.isArray(perTickers) && perTickers.length) return [...perTickers];
    } catch (_) {}
    return ['AAPL', 'NVDA', '005930.KS', '000660.KS'];
  }

  function displayName(symbol, localNames, valuation) {
    try { if (typeof tickerNameMap !== 'undefined' && tickerNameMap[symbol]) return tickerNameMap[symbol]; } catch (_) {}
    try { if (typeof perTickerNameMap !== 'undefined' && perTickerNameMap[symbol]) return perTickerNameMap[symbol]; } catch (_) {}
    return localNames.get(symbol) || valuation?.quotes?.[symbol]?.shortName || symbol;
  }

  function loadSources() {
    if (!sourcePromise) {
      sourcePromise = Promise.all([
        fetch('/static/data/screener.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : { stocks: [] }).catch(() => ({ stocks: [] })),
        fetch('/static/data/consensus_cache.json', { cache: 'no-store' }).then((r) => r.ok ? r.json() : { quotes: {} }).catch(() => ({ quotes: {} })),
        fetch('/static/data/valuation_cache.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : { quotes: {} }).catch(() => ({ quotes: {} })),
        fetch('/api/macro', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null).catch(() => null),
      ]);
    }
    return sourcePromise;
  }

  function watchItems(screener, consensus, valuation) {
    const stocks = screener.stocks || [];
    const tech = new Map(stocks.map((row) => [row.symbol, row]));
    const names = new Map(stocks.map((row) => [row.symbol, row.name]));
    const selected = [...new Set(selectedTickersNow())].slice(0, 6);
    return selected.map((symbol) => {
      const row = tech.get(symbol) || {};
      const c = (consensus.quotes || {})[symbol] || {};
      let change = num(row.change1d);
      let changeLabel = '오늘';
      if (change === null) {
        change = num((c.priceTrend || {}).return30);
        changeLabel = '30D';
      }
      return {
        symbol,
        name: displayName(symbol, names, valuation),
        change,
        changeLabel,
        price: num(row.price ?? valuation?.quotes?.[symbol]?.regularMarketPrice),
      };
    });
  }

  function buildConsensusRows(consensus, screener) {
    const names = new Map((screener.stocks || []).map((row) => [row.symbol, row.name]));
    return Object.entries(consensus.quotes || {}).map(([symbol, quote]) => {
      const period = (quote.periods || {})['0y'] || {};
      const trend = period.epsTrend || {};
      const revisions = period.revisions || {};
      const eps30 = revisionPct(trend.current ?? (period.earnings || {}).avg, trend['30daysAgo']);
      return {
        symbol,
        name: names.get(symbol) || quote.name || symbol,
        eps30,
        analysts: num((period.earnings || {}).analysts) || 0,
        up30: num(revisions.up30) || 0,
        down30: num(revisions.down30) || 0,
      };
    });
  }

  function buildIssues(screener, consensus, macro) {
    const issues = [];
    const revision = buildConsensusRows(consensus, screener)
      .filter((row) => row.eps30 !== null && row.eps30 > 0 && row.analysts >= 2 && row.up30 >= row.down30)
      .sort((a, b) => b.eps30 - a.eps30)[0];
    if (revision) {
      issues.push({
        type: 'stock', symbol: revision.symbol, name: revision.name,
        title: `${revision.name}, EPS 기대치 30일 ${pct(revision.eps30)} 상향`,
        sub: `상향 ${Math.round(revision.up30)} · 하향 ${Math.round(revision.down30)} · 애널리스트 ${Math.round(revision.analysts)}명`,
      });
    }

    const volume = (screener.stocks || [])
      .filter((row) => num(row.volumeRatio) !== null && num(row.volumeRatio) >= 1.5)
      .sort((a, b) => num(b.volumeRatio) - num(a.volumeRatio))[0];
    if (volume) {
      issues.push({
        type: 'stock', symbol: volume.symbol, name: volume.name,
        title: `${volume.name}, 거래량 ${num(volume.volumeRatio).toFixed(1)}배로 확대`,
        sub: `20일 ${pct(volume.ret20)} · RSI ${num(volume.rsi14) === null ? '-' : num(volume.rsi14).toFixed(1)} · 기술점수 ${Math.round(num(volume.score) || 0)}`,
      });
    }

    if (macro) {
      const summary = typeof macro.summary === 'string' ? macro.summary : macro.summary?.text;
      issues.push({
        type: 'macro',
        title: summary || '오늘의 시장 환경 데이터가 갱신됐습니다.',
        sub: Number(macro.staleCount || 0) ? '일부 지표 갱신 지연 · 시장 탭에서 확인' : '주요 매크로 데이터 정상 갱신',
      });
    }
    return issues.slice(0, 3);
  }

  function signalLabel(row) {
    if (num(row.volumeRatio) !== null && num(row.volumeRatio) >= 2) return ['volume', '거래량'];
    if (num(row.rsi14) !== null && num(row.rsi14) <= 35) return ['oversold', '과매도'];
    if (row.cross20 === true) return ['cross', '돌파'];
    if (row.aligned === true) return ['trend', '정배열'];
    return ['chance', '기회'];
  }

  function buildSignals(screener) {
    return (screener.stocks || [])
      .filter((row) => num(row.score) !== null && num(row.score) >= 52 && (num(row.volumeRatio) >= 1.2 || row.cross20 || row.aligned || num(row.rsi14) <= 35))
      .sort((a, b) => (num(b.score) - num(a.score)) || (num(b.volumeRatio) - num(a.volumeRatio)))
      .slice(0, 5);
  }

  function timeBadge() {
    try {
      return new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date()).replace(/\. /g, '.').replace('.', '.');
    } catch (_) {
      return '최신';
    }
  }

  function watchHtml(items) {
    return `
      <section class="home14-card home14-watch" data-home14-section="watch">
        <div class="home14-head"><h3>내 관심 브리핑</h3><span>${esc(timeBadge())}</span></div>
        <div class="home14-watch-row">${items.map((item) => `
          <button type="button" class="home14-watch-item" data-home14-symbol="${esc(item.symbol)}" data-home14-name="${esc(item.name)}">
            <span class="home14-logo-ring">${logoMarkup(item.symbol, item.name)}<i>N</i></span>
            <strong>${esc(item.name)}</strong>
            <small>${esc(item.changeLabel)}</small>
            <b class="${(item.change || 0) >= 0 ? 'up' : 'down'}">${pct(item.change, 2)}</b>
          </button>`).join('')}</div>
      </section>`;
  }

  function issueThumb(issue) {
    if (issue.type === 'stock') return `<span class="home14-issue-thumb">${logoMarkup(issue.symbol, issue.name, 'square')}</span>`;
    return '<span class="home14-issue-thumb home14-macro-thumb">◎</span>';
  }

  function issuesHtml(issues) {
    return `
      <section class="home14-card home14-issues" data-home14-section="issues">
        <div class="home14-head"><h3>오늘 주요 이슈</h3><span>${esc(timeBadge())}</span></div>
        <div class="home14-issue-list">${issues.map((issue) => `
          <button type="button" class="home14-issue-row" ${issue.symbol ? `data-home14-symbol="${esc(issue.symbol)}" data-home14-name="${esc(issue.name)}"` : 'data-home14-market="1"'}>
            <span class="home14-issue-copy"><strong>${esc(issue.title)}</strong><small>${esc(issue.sub)}</small></span>
            ${issueThumb(issue)}
          </button>`).join('')}</div>
        <button type="button" class="home14-more" data-home14-discover>더 많은 후보 보기 <b>›</b></button>
      </section>`;
  }

  function signalsHtml(rows) {
    return `
      <section class="home14-card home14-signals" data-home14-section="signals">
        <div class="home14-head"><h3>새로 포착된 시그널</h3><span>장마감 데이터</span></div>
        <div class="home14-signal-list">${rows.map((row) => {
          const [cls, label] = signalLabel(row);
          const detail = `${num(row.volumeRatio) === null ? '거래량 -' : `거래량 ${num(row.volumeRatio).toFixed(1)}x`} · RSI ${num(row.rsi14) === null ? '-' : num(row.rsi14).toFixed(1)} · 20일 ${pct(row.ret20)}`;
          return `
            <button type="button" class="home14-signal-row" data-home14-symbol="${esc(row.symbol)}" data-home14-name="${esc(row.name)}">
              <span class="home14-signal-badge ${cls}">${label}</span>
              ${logoMarkup(row.symbol, row.name, 'mini')}
              <span class="home14-signal-copy"><strong>${esc(row.name)}</strong><small>${esc(detail)}</small></span>
              <time>${Math.round(num(row.score) || 0)}점</time>
              <i>›</i>
            </button>`;
        }).join('')}</div>
      </section>`;
  }

  function bindLogoFallbacks(root) {
    qsa('img[data-home14-logo]', root).forEach((img) => {
      img.addEventListener('error', () => img.classList.add('broken'), { once: true });
    });
  }

  function openStock(symbol, name) {
    if (typeof window.addGlobalTicker === 'function') window.addGlobalTicker(symbol, name);
    if (typeof window.__focusStockBrief === 'function') window.__focusStockBrief(symbol);
    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');
    else if (typeof window.switchTab === 'function') window.switchTab('chart');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function bindActions(root) {
    qsa('[data-home14-symbol]', root).forEach((button) => {
      button.addEventListener('click', () => openStock(button.dataset.home14Symbol, button.dataset.home14Name));
    });
    qsa('[data-home14-market]', root).forEach((button) => button.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('macro');
      else if (typeof window.switchTab === 'function') window.switchTab('macro');
    }));
    qs('[data-home14-discover]', root)?.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('screener');
      else if (typeof window.switchTab === 'function') window.switchTab('screener');
    });
  }

  function installNavIcons() {
    const icons = {
      home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 10.5 12 3.8l8.5 6.7v9a1 1 0 0 1-1 1h-5.1v-6.1H9.6v6.1H4.5a1 1 0 0 1-1-1z"/></svg>',
      analysis: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19V9m7 10V5m7 14v-7"/><circle cx="5" cy="8" r="1.5"/><circle cx="12" cy="4" r="1.5"/><circle cx="19" cy="11" r="1.5"/></svg>',
      discover: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 14.6 9l5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1L9.4 9z"/></svg>',
      market: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="m9.2 14.8 2-5 4-1.6-1.6 4z"/></svg>',
    };
    const labels = { home: '홈', analysis: '분석', discover: '발굴', market: '시장' };
    qsa('.app-bottom-btn[data-app-mode]').forEach((button) => {
      const mode = button.dataset.appMode;
      const icon = qs('.app-bottom-icon', button);
      if (icon && icons[mode]) icon.innerHTML = icons[mode];
      const spans = qsa(':scope > span', button);
      if (spans[1] && labels[mode]) spans[1].textContent = labels[mode];
    });
  }

  async function renderHome14() {
    const root = qs('#home-v8-body');
    if (!root || renderBusy) { renderQueued = true; return false; }
    renderBusy = true;
    try {
      const [screener, consensus, valuation, macro] = await loadSources();
      if (!document.body.contains(root)) return false;
      qsa('.home14-stack', root).forEach((node) => node.remove());
      const wrap = document.createElement('div');
      wrap.className = 'home14-stack';
      wrap.innerHTML = watchHtml(watchItems(screener, consensus, valuation)) + issuesHtml(buildIssues(screener, consensus, macro)) + signalsHtml(buildSignals(screener));
      root.insertAdjacentElement('afterbegin', wrap);
      root.classList.add('home-v14-ready');
      bindLogoFallbacks(wrap);
      bindActions(wrap);

      const hero = qs('.home-v8-hero');
      if (hero) {
        const h2 = qs('h2', hero); if (h2) h2.textContent = '오늘의 투자 브리핑';
        const p = qs('p', hero); if (p) p.textContent = '관심 종목과 새로 포착된 신호를 한 화면에서 확인하세요.';
      }
      return true;
    } finally {
      renderBusy = false;
      if (renderQueued) {
        renderQueued = false;
        setTimeout(renderHome14, 50);
      }
    }
  }

  function boot() {
    installNavIcons();
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      installNavIcons();
      if (qs('#home-v8-body') && !qs('#home-v8-body .home14-stack')) renderHome14();
      if (attempts >= 30) clearInterval(timer);
    }, 300);

    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(renderHome14, 220);
    });

    const observer = new MutationObserver((mutations) => {
      const changed = mutations.some((m) => Array.from(m.addedNodes || []).some((node) => node.nodeType === 1 && !node.closest?.('.home14-stack')));
      if (changed && qs('#home-v8-body')) setTimeout(renderHome14, 80);
      installNavIcons();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 12000);
  }

  window.__renderHomeCardsV14 = renderHome14;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
