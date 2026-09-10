// Evidence-based investment ideas built from existing valuation + price data.
(() => {
  'use strict';

  let screenerPromise = null;
  let quoteCachePromise = null;
  let loadSeq = 0;

  const esc = (v) => String(v ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  const num = (v, d = 1) => (v === null || v === undefined || !Number.isFinite(Number(v))) ? '-' : Number(v).toFixed(d);
  const pct = (v) => (v === null || v === undefined || !Number.isFinite(Number(v))) ? '-' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(1)}%`;

  function selected() {
    if (typeof perTickers !== 'undefined' && Array.isArray(perTickers)) return [...perTickers];
    if (typeof selectedTickers !== 'undefined' && Array.isArray(selectedTickers)) return [...selectedTickers];
    return ['AAPL', 'NVDA'];
  }

  function installTab() {
    const nav = document.querySelector('.tab-nav');
    if (!nav || nav.querySelector('[data-tab="ideas"]')) return;
    const btn = document.createElement('button');
    btn.className = 'tab-btn';
    btn.dataset.tab = 'ideas';
    btn.textContent = '💡 투자 아이디어';
    const valuation = nav.querySelector('[data-tab="fwdper"]');
    if (valuation) valuation.insertAdjacentElement('afterend', btn); else nav.appendChild(btn);

    const tab = document.createElement('div');
    tab.id = 'ideas-tab';
    tab.className = 'tab-content';
    tab.innerHTML = `
      <section class="ideas-section">
        <div class="ideas-head">
          <div>
            <h2>💡 선택 종목 투자 아이디어</h2>
            <p>가치·수익성·전망·모멘텀을 실제 데이터로 나눠 보여줍니다. 단일 매수점수가 아니라 관찰 근거를 제공합니다.</p>
          </div>
          <button id="ideas-refresh" class="ideas-refresh" type="button">새로고침</button>
        </div>
        <div class="ideas-method">가치/수익성: Yahoo Fundamentals · 전망: Yahoo 컨센서스(있는 경우) · 모멘텀: Yahoo Chart 또는 한국 장마감 스크리너</div>
        <div id="ideas-summary" class="ideas-summary">탭을 열면 선택 종목을 분석합니다.</div>
        <div id="ideas-grid" class="ideas-grid"><div class="ideas-empty">분석할 종목을 선택해 주세요.</div></div>
      </section>`;
    const macro = document.getElementById('macro-tab');
    if (macro) macro.insertAdjacentElement('beforebegin', tab);
    else document.getElementById('app')?.appendChild(tab);

    btn.addEventListener('click', () => {
      if (typeof window.switchTab === 'function') window.switchTab('ideas');
      loadIdeas();
    });
    tab.querySelector('#ideas-refresh')?.addEventListener('click', loadIdeas);
  }

  function loadScreener() {
    if (!screenerPromise) {
      screenerPromise = fetch('/static/data/screener.json', { cache: 'force-cache' })
        .then((r) => r.ok ? r.json() : { stocks: [] })
        .catch(() => ({ stocks: [] }));
    }
    return screenerPromise;
  }

  function loadQuoteCache() {
    if (!quoteCachePromise) {
      quoteCachePromise = fetch('/static/data/valuation_cache.json', { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : { quotes: {} })
        .catch(() => ({ quotes: {} }));
    }
    return quoteCachePromise;
  }

  function calcMomentum(stock, screenRow) {
    if (screenRow) {
      return {
        rsi: screenRow.rsi14,
        ret20: screenRow.ret20,
        ret60: screenRow.ret60,
        aligned: !!screenRow.aligned,
        cross20: !!screenRow.cross20,
        source: `KRX ${screenRow.date || '-'} 장마감 배치`,
      };
    }
    return { rsi: null, ret20: null, ret60: null, aligned: false, cross20: false, source: '모멘텀 상세 데이터 없음' };
  }

  function outlook(stock, quote) {
    const trailing = Number(stock.trailingPE);
    const forward = Number(stock.forwardPE ?? quote?.forwardPE);
    if (!Number.isFinite(forward) || forward <= 0) return { label: '전망 데이터 없음', tone: 'neutral', detail: 'FWD PER 컨센서스 미제공' };
    if (Number.isFinite(trailing) && trailing > 0) {
      const gap = (forward / trailing - 1) * 100;
      if (gap <= -12) return { label: '이익 개선 기대', tone: 'good', detail: `FWD PER가 실적 PER보다 ${Math.abs(gap).toFixed(0)}% 낮음` };
      if (gap >= 15) return { label: '전망 부담', tone: 'warn', detail: `FWD PER가 실적 PER보다 ${gap.toFixed(0)}% 높음` };
    }
    return { label: '전망 중립', tone: 'neutral', detail: `FWD PER ${forward.toFixed(1)}배` };
  }

  function buildSignals(stock, screenRow, quote) {
    const positives = [];
    const cautions = [];
    const pe = Number(stock.trailingPE);
    const pbr = Number(stock.pbr);
    const roe = Number(stock.roe);
    const margin = Number(stock.operatingMargin);
    const momentum = calcMomentum(stock, screenRow);
    const outlookInfo = outlook(stock, quote);

    if (Number.isFinite(pe) && pe > 0 && pe <= 15) positives.push(`PER ${pe.toFixed(1)}배`);
    else if (Number.isFinite(pe) && pe >= 40) cautions.push(`PER ${pe.toFixed(1)}배`);

    if (Number.isFinite(pbr) && pbr > 0 && pbr <= 2) positives.push(`PBR ${pbr.toFixed(1)}배`);
    if (Number.isFinite(roe) && roe >= 15) positives.push(`ROE ${roe.toFixed(1)}%`);
    else if (Number.isFinite(roe) && roe < 5) cautions.push(`ROE ${roe.toFixed(1)}%`);
    if (Number.isFinite(margin) && margin >= 15) positives.push(`영업이익률 ${margin.toFixed(1)}%`);

    if (momentum.aligned) positives.push('20·60·120일 정배열');
    else if (momentum.cross20) positives.push('20일선 돌파');
    if (Number.isFinite(momentum.ret20) && momentum.ret20 >= 8) positives.push(`20일 ${pct(momentum.ret20)}`);
    if (Number.isFinite(momentum.ret20) && momentum.ret20 <= -12) cautions.push(`20일 ${pct(momentum.ret20)}`);
    if (Number.isFinite(momentum.rsi) && momentum.rsi >= 70) cautions.push(`RSI ${momentum.rsi.toFixed(1)} 과열`);
    if (Number.isFinite(momentum.rsi) && momentum.rsi <= 35) positives.push(`RSI ${momentum.rsi.toFixed(1)} 과매도권`);

    if (outlookInfo.tone === 'good') positives.push(outlookInfo.label);
    if (outlookInfo.tone === 'warn') cautions.push(outlookInfo.label);

    const fields = ['trailingPE', 'pbr', 'roe', 'operatingMargin', 'forwardPE'];
    const complete = fields.filter((k) => stock[k] !== null && stock[k] !== undefined && Number.isFinite(Number(stock[k]))).length;
    const completeness = Math.round(complete / fields.length * 100);

    let status = '조건 혼재';
    let tone = 'neutral';
    if (positives.length >= 3 && cautions.length <= 1) { status = '관찰 우선'; tone = 'good'; }
    if (cautions.length >= 3) { status = '주의 필요'; tone = 'warn'; }

    return { positives, cautions, momentum, outlookInfo, completeness, status, tone };
  }

  function card(stock, screenRow, quote, tradeDate) {
    const s = buildSignals(stock, screenRow, quote);
    const sourceDate = quote ? (tradeDate || '') : '';
    const analyst = quote?.averageAnalystRating ? esc(quote.averageAnalystRating) : '없음';
    const positiveHtml = s.positives.length ? s.positives.slice(0, 5).map((x) => `<span class="idea-chip good">${esc(x)}</span>`).join('') : '<span class="idea-chip neutral">강한 긍정 신호 없음</span>';
    const cautionHtml = s.cautions.length ? s.cautions.slice(0, 4).map((x) => `<span class="idea-chip warn">${esc(x)}</span>`).join('') : '<span class="idea-chip neutral">뚜렷한 경고 신호 없음</span>';
    return `
      <article class="idea-card">
        <div class="idea-card-top">
          <div><div class="idea-name">${esc(stock.name || stock.ticker)}</div><div class="idea-ticker">${esc(stock.ticker)}</div></div>
          <span class="idea-status ${s.tone}">${s.status}</span>
        </div>
        <div class="idea-axis-grid">
          <div><span>PER</span><strong>${num(stock.trailingPE)}x</strong></div>
          <div><span>PBR</span><strong>${num(stock.pbr)}x</strong></div>
          <div><span>ROE</span><strong>${num(stock.roe)}%</strong></div>
          <div><span>영업이익률</span><strong>${num(stock.operatingMargin)}%</strong></div>
          <div><span>FWD PER</span><strong>${num(stock.forwardPE ?? quote?.forwardPE)}x</strong></div>
          <div><span>20일 수익률</span><strong>${pct(s.momentum.ret20)}</strong></div>
        </div>
        <div class="idea-block"><div class="idea-block-title">볼 이유</div><div class="idea-chips">${positiveHtml}</div></div>
        <div class="idea-block"><div class="idea-block-title">확인할 위험</div><div class="idea-chips">${cautionHtml}</div></div>
        <div class="idea-foot">
          <span>애널리스트: ${analyst}</span>
          <span>데이터 완성도 ${s.completeness}%</span>
          <span>${esc(s.momentum.source)}</span>
        </div>
      </article>`;
  }

  async function loadIdeas() {
    const seq = ++loadSeq;
    const tickers = selected().slice(0, 6);
    const grid = document.getElementById('ideas-grid');
    const summary = document.getElementById('ideas-summary');
    if (!grid || !summary) return;
    if (!tickers.length) {
      summary.textContent = '선택 종목 0개';
      grid.innerHTML = '<div class="ideas-empty">차트 또는 밸류에이션에서 종목을 먼저 선택해 주세요.</div>';
      return;
    }

    summary.textContent = '선택 종목 데이터를 확인하는 중...';
    grid.innerHTML = '<div class="ideas-loading"><div class="spinner"></div><span>투자 근거를 정리하는 중...</span></div>';

    try {
      const [valuation, screener, quoteCache] = await Promise.all([
        fetch(`/api/valuation?tickers=${encodeURIComponent(tickers.join(','))}`, { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`valuation ${r.status}`);
          return r.json();
        }),
        loadScreener(),
        loadQuoteCache(),
      ]);
      if (seq !== loadSeq) return;
      const stocks = Array.isArray(valuation.stocks) ? valuation.stocks : [];
      const screenMap = new Map((screener.stocks || []).map((r) => [r.symbol, r]));
      const quotes = quoteCache.quotes || {};
      summary.textContent = `${stocks.length}개 종목 · 가치/수익성/전망/모멘텀을 분리 평가 · 단일 매수점수 아님`;
      grid.innerHTML = stocks.map((stock) => card(stock, screenMap.get(stock.ticker), quotes[stock.ticker], screener.tradeDate)).join('') || '<div class="ideas-empty">분석 가능한 데이터가 없습니다.</div>';
    } catch (err) {
      console.error('Ideas load failed', err);
      if (seq === loadSeq) {
        summary.textContent = '데이터를 불러오지 못했습니다.';
        grid.innerHTML = '<div class="ideas-empty">잠시 후 새로고침해 주세요.</div>';
      }
    }
  }

  function init() {
    installTab();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
