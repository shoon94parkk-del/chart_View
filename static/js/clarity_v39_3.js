(() => {
  'use strict';

  const SELECTED_KEY = 'chartview-selected-tickers-v1';
  const DETAIL_ID = 'stock-detail-v36';
  let origin = null;
  let detailWasOpen = false;
  let detailObserver = null;
  const basisCache = new Map();
  const basisInflight = new Map();

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const num = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const pct = (value, digits = 1) => {
    const n = num(value);
    return n === null ? '-' : `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
  };
  const mult = (value) => {
    const n = num(value);
    return n === null ? '-' : `${n.toFixed(1)}x`;
  };

  function selectedSymbols() {
    try {
      const raw = JSON.parse(localStorage.getItem(SELECTED_KEY) || '[]');
      return Array.isArray(raw) ? raw.map((x) => String(x).toUpperCase()) : [];
    } catch (_) { return []; }
  }

  function activeMode() {
    const button = document.querySelector('.app-bottom-btn.active[data-app-mode]');
    if (button?.dataset.appMode) return button.dataset.appMode;
    const active = document.querySelector('.tab-content.active');
    return active?.id?.replace(/-tab$/, '') || 'home';
  }

  function captureOrigin(event) {
    const node = event.target?.closest?.('[data-home-symbol], [data-home-watch-open], [data-watch-open], [data-watch-recent], [data-news-v38-chart]');
    if (!node || node.closest(`#${DETAIL_ID}`)) return;
    origin = { mode: activeMode(), scrollY: window.scrollY, capturedAt: Date.now() };
  }

  function detailSymbol(section) {
    return String(section?.querySelector('.v36-detail-head small')?.textContent || '').trim().toUpperCase();
  }

  function detailName(section) {
    return String(section?.querySelector('.v36-detail-head h2')?.textContent || detailSymbol(section)).trim();
  }

  function currentPrice(section) {
    return String(section?.querySelector('.v36-detail-head > strong')?.textContent || '-').trim();
  }

  function metricValue(section, label) {
    const rows = [...(section?.querySelectorAll('.v36-detail-metrics > div') || [])];
    const hit = rows.find((row) => row.querySelector('span')?.textContent?.includes(label));
    return String(hit?.querySelector('strong')?.textContent || '-').trim();
  }

  function ensureContext(section) {
    if (!section || section.hidden) return;
    const symbol = detailSymbol(section);
    if (!symbol) return;
    const selected = selectedSymbols();
    const already = selected.includes(symbol);
    let context = section.querySelector('.v393-detail-context');
    if (!context) {
      context = document.createElement('div');
      context.className = 'v393-detail-context';
      section.querySelector('.v36-detail-head')?.insertAdjacentElement('afterend', context);
    }
    context.innerHTML = `
      <span class="v393-target">상세 대상 <b>${esc(detailName(section))}</b></span>
      <span class="v393-compare ${already ? 'in' : ''}">${already ? '비교목록 · 이미 포함' : `비교목록 · ${selected.length}/6`}</span>`;
  }

  async function loadTargetEvidence(symbol) {
    const [valuationResult, consensusResult] = await Promise.allSettled([
      fetch(`/api/valuation?tickers=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
      fetch(`/api/consensus?ticker=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
    ]);
    const valuation = valuationResult.status === 'fulfilled' ? valuationResult.value : null;
    const consensus = consensusResult.status === 'fulfilled' ? consensusResult.value : null;
    const value = valuation?.stocks?.[0] || valuation?.quotes?.[symbol] || {};
    const period = consensus?.periods?.['0y'] || consensus?.quote?.periods?.['0y'] || {};
    const trend = period?.epsTrend || {};
    const current = num(trend.current ?? period?.earnings?.avg);
    const prior = num(trend['30daysAgo']);
    const eps30 = current !== null && prior !== null && current > 0 && prior > 0 ? (current / prior - 1) * 100 : null;
    return { value, eps30 };
  }

  function ensureTargetActions(section) {
    if (!section || section.hidden || section.querySelector('.v393-target-actions')) return;
    const symbol = detailSymbol(section);
    if (!symbol || !section.querySelector('.v36-detail-actions')) return;
    const wrap = document.createElement('div');
    wrap.className = 'v393-target-actions';
    wrap.innerHTML = `
      <button type="button" data-v393-value>밸류 보기</button>
      <button type="button" data-v393-decision>투자판단 보기</button>
      <span>두 버튼은 비교목록이 아니라 현재 상세 대상만 확인합니다.</span>
      <div class="v393-target-panel" hidden></div>`;
    section.querySelector('.v36-detail-actions').insertAdjacentElement('beforebegin', wrap);

    const panel = wrap.querySelector('.v393-target-panel');
    let evidencePromise = null;
    const evidence = () => evidencePromise || (evidencePromise = loadTargetEvidence(symbol));

    wrap.querySelector('[data-v393-value]')?.addEventListener('click', async () => {
      panel.hidden = false;
      panel.innerHTML = '<div class="v393-panel-loading">밸류 데이터를 불러오는 중…</div>';
      const { value } = await evidence();
      if (detailSymbol(section) !== symbol) return;
      panel.innerHTML = `
        <div class="v393-panel-head"><strong>${esc(detailName(section))} · 밸류</strong><small>상세 대상 전용</small></div>
        <div class="v393-panel-grid">
          <div><span>현재가</span><b>${esc(currentPrice(section))}</b></div>
          <div><span>FWD PER</span><b>${mult(value?.forwardPE)}</b></div>
          <div><span>PER</span><b>${mult(value?.trailingPE ?? value?.trailingPe)}</b></div>
          <div><span>ROE</span><b>${pct((num(value?.roe) ?? 0) * (Math.abs(num(value?.roe) ?? 0) <= 1 ? 100 : 1), 1)}</b></div>
        </div>
        <p>비교목록은 변경하지 않았습니다. 값이 없으면 제공처 미제공 또는 계산 불가일 수 있습니다.</p>`;
    });

    wrap.querySelector('[data-v393-decision]')?.addEventListener('click', async () => {
      panel.hidden = false;
      panel.innerHTML = '<div class="v393-panel-loading">판단 근거를 불러오는 중…</div>';
      const { value, eps30 } = await evidence();
      if (detailSymbol(section) !== symbol) return;
      panel.innerHTML = `
        <div class="v393-panel-head"><strong>${esc(detailName(section))} · 투자판단 근거</strong><small>매수점수 아님</small></div>
        <div class="v393-panel-grid">
          <div><span>1달 수익률</span><b>${esc(metricValue(section, '1달 수익률'))}</b></div>
          <div><span>EPS 전망 30일</span><b>${eps30 === null ? '-' : pct(eps30, 1)}</b></div>
          <div><span>FWD PER</span><b>${mult(value?.forwardPE)}</b></div>
          <div><span>ROE</span><b>${pct((num(value?.roe) ?? 0) * (Math.abs(num(value?.roe) ?? 0) <= 1 ? 100 : 1), 1)}</b></div>
        </div>
        <p>현재 상세 대상의 공개 데이터 근거만 모아 보여줍니다. 업종·전망 기간·재무구조 등 추가 확인이 필요합니다.</p>`;
    });
  }

  function normalizeDetailBasis(section) {
    if (!section || section.hidden) return;
    const basis = section.querySelector('.v36-detail-basis');
    if (!basis || basis.querySelector('.v393-basis-extra')) return;
    const range = [...basis.querySelectorAll('span')].find((x) => x.querySelector('b')?.textContent?.includes('실제 비교 구간'))?.textContent || '';
    const end = range.match(/(\d{4}-\d{2}-\d{2})(?!.*\d{4}-\d{2}-\d{2})/)?.[1];
    const extra = document.createElement('span');
    extra.className = 'v393-basis-extra';
    extra.innerHTML = `<b>거래 기준</b>${esc(end || '확인 불가')}<small> · 조회 ${new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date())}</small>`;
    basis.appendChild(extra);
  }

  function syncDetailState() {
    const section = document.getElementById(DETAIL_ID);
    const open = Boolean(section && !section.hidden && section.textContent.trim());
    document.body.classList.toggle('v393-detail-open', open);
    if (open) {
      detailWasOpen = true;
      ensureContext(section);
      ensureTargetActions(section);
      normalizeDetailBasis(section);
    } else if (detailWasOpen) {
      detailWasOpen = false;
      if (origin && Date.now() - origin.capturedAt < 30 * 60 * 1000) {
        const restore = origin;
        origin = null;
        setTimeout(() => {
          if (restore.mode && restore.mode !== 'chart' && typeof window.__openAppTab === 'function') {
            window.__openAppTab(restore.mode);
          }
          setTimeout(() => window.scrollTo({ top: restore.scrollY, behavior: 'auto' }), 50);
        }, 0);
      }
    }
  }

  function watchDetail() {
    const section = document.getElementById(DETAIL_ID);
    if (!section || detailObserver) return;
    detailObserver = new MutationObserver(syncDetailState);
    detailObserver.observe(section, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden'] });
    syncDetailState();
  }

  const shortDate = (raw) => {
    const text = String(raw || '');
    const m = text.match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[2]}.${m[3]}` : '';
  };

  async function fetchBasis(symbols) {
    const missing = symbols.filter((symbol) => !basisCache.has(symbol));
    for (let i = 0; i < missing.length; i += 6) {
      const chunk = missing.slice(i, i + 6);
      const key = chunk.join(',');
      if (basisInflight.has(key)) { await basisInflight.get(key); continue; }
      const job = fetch(`/api/compare?tickers=${encodeURIComponent(key)}&period=1mo`, { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          (data?.stocks || []).forEach((stock) => {
            const symbol = String(stock.ticker || '').toUpperCase();
            const end = stock.actualEnd || stock.endDate || stock?.meta?.actualEnd || stock?.meta?.end || '';
            if (symbol) basisCache.set(symbol, end);
          });
        }).catch(() => null).finally(() => basisInflight.delete(key));
      basisInflight.set(key, job);
      await job;
    }
  }

  async function decorateWatchlistBasis() {
    const homeButtons = [...document.querySelectorAll('[data-home-watch-open]')];
    const gridButtons = [...document.querySelectorAll('[data-watch-open]')];
    const symbols = [...new Set([...homeButtons, ...gridButtons].map((x) => String(x.dataset.homeWatchOpen || x.dataset.watchOpen || '').toUpperCase()).filter(Boolean))];
    if (!symbols.length) return;
    await fetchBasis(symbols);
    homeButtons.forEach((button) => {
      const symbol = String(button.dataset.homeWatchOpen || '').toUpperCase();
      let meta = button.querySelector('.v393-home-basis');
      if (!meta) {
        meta = document.createElement('span');
        meta.className = 'v393-home-basis';
        button.appendChild(meta);
      }
      const date = shortDate(basisCache.get(symbol));
      meta.textContent = `${date ? `${date} 거래 · ` : ''}1달 수익률`;
    });
    gridButtons.forEach((button) => {
      const symbol = String(button.dataset.watchOpen || '').toUpperCase();
      const meta = button.querySelector('.watchlist-v30-meta');
      const date = shortDate(basisCache.get(symbol));
      if (meta) meta.textContent = `${date ? `${date} 거래 · ` : ''}1달 수익률 · 조회 기준`;
    });
  }

  function normalizeCopies() {
    document.querySelectorAll('.watchlist-v30-meta').forEach((node) => {
      node.textContent = node.textContent.replace('방금 갱신', '방금 조회').replace('저장된 시세', '이전 조회');
    });
    document.querySelectorAll('.home16-summary-foot').forEach((node) => {
      node.textContent = node.textContent.replace('최근 기준', '매크로 관측 기준');
    });
    document.querySelectorAll('[data-home-watch-return]').forEach((node) => {
      if (!node.querySelector('.v393-period')) node.insertAdjacentHTML('beforeend', '<span class="v393-period">1달</span>');
    });
  }

  function refreshDecorations() {
    watchDetail();
    normalizeCopies();
    decorateWatchlistBasis().catch(() => {});
  }

  function init() {
    window.addEventListener('click', captureOrigin, true);
    const observer = new MutationObserver(() => {
      clearTimeout(observer._timer);
      observer._timer = setTimeout(refreshDecorations, 30);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    document.addEventListener('chartview:watchlist-change', refreshDecorations);
    document.addEventListener('chartview:v37-news-rendered', refreshDecorations);
    refreshDecorations();
    setTimeout(refreshDecorations, 600);
    setTimeout(refreshDecorations, 1800);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
