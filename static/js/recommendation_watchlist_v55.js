(() => {
  'use strict';

  if (window.__chartViewRecommendationWatchlistV55Installed) return;
  window.__chartViewRecommendationWatchlistV55Installed = true;

  const HOME_VISIBLE = 4;
  const REC_URL = '/static/data/ai_recommendations.json';
  const QUOTE_CACHE_KEY = 'chartview-watchlist-quotes-v33';
  let recommendations = new Map();
  let queued = false;
  let observer = null;

  const n = (value) => {
    const x = Number(value);
    return Number.isFinite(x) ? x : null;
  };

  function safeJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) { return fallback; }
  }

  function latestRecommendations(rows) {
    const map = new Map();
    for (const row of Array.isArray(rows) ? rows : []) {
      const symbol = String(row?.symbol || '').trim().toUpperCase();
      const base = n(row?.recommendedPrice);
      const date = String(row?.recommendedDate || '').slice(0, 10);
      if (!symbol || base === null || base <= 0 || !date) continue;
      const prev = map.get(symbol);
      if (!prev || date > prev.recommendedDate) map.set(symbol, { ...row, symbol, recommendedDate: date, recommendedPrice: base });
    }
    return map;
  }

  async function loadRecommendations() {
    try {
      const response = await fetch(`${REC_URL}?v=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      recommendations = latestRecommendations(payload?.recommendations);
    } catch (_) {
      recommendations = new Map();
    }
    schedule();
  }

  function quoteMap() {
    const cache = safeJson(QUOTE_CACHE_KEY, { quotes: {} });
    return cache && typeof cache === 'object' && cache.quotes && typeof cache.quotes === 'object' ? cache.quotes : {};
  }

  function currentPrice(symbol, rec, quotes) {
    const live = n(quotes?.[symbol]?.price);
    if (live !== null && live > 0) return live;
    const tracked = n(rec?.currentPrice);
    return tracked !== null && tracked > 0 ? tracked : null;
  }

  function calcRecommendationReturn(current, recommendedPrice) {
    const currentValue = n(current);
    const base = n(recommendedPrice);
    if (currentValue === null || base === null || base <= 0) return null;
    return (currentValue / base - 1) * 100;
  }

  function formatPrice(symbol, value) {
    const price = n(value);
    if (price === null) return '—';
    if (/\.(KS|KQ)$/.test(symbol)) return `₩${Math.round(price).toLocaleString('ko-KR')}`;
    return `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function formatReturn(value) {
    const x = n(value);
    if (x === null) return '추천 기록 없음';
    return `${x > 0 ? '+' : ''}${x.toFixed(2)}%`;
  }

  function returnClass(value) {
    const x = n(value);
    return x === null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
  }

  function dateLabel(value) {
    const m = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return m ? `${m[2]}.${m[3]}` : String(value || '');
  }

  function performance(symbol, quotes) {
    const rec = recommendations.get(symbol);
    if (!rec) return { rec: null, current: n(quotes?.[symbol]?.price), ret: null };
    const current = currentPrice(symbol, rec, quotes);
    return { rec, current, ret: calcRecommendationReturn(current, rec.recommendedPrice) };
  }

  function ensureStyle() {
    if (document.getElementById('recommendation-watchlist-v55-style')) return;
    const style = document.createElement('style');
    style.id = 'recommendation-watchlist-v55-style';
    style.textContent = `
      .watch-rec-baseline-v55{display:block;margin-top:6px;color:#8b95a1;font-size:11px;font-weight:650;line-height:1.35;letter-spacing:-.02em}
      #home-watchlist-v30 .watch-rec-baseline-v55{grid-column:1/-1;margin-top:5px;font-size:10.5px}
      #home-watchlist-v30 [data-home-watch-return].no-rec-v55{font-size:10px;color:#8b95a1;background:#f2f4f6;padding:5px 7px;border-radius:999px}
      #watchlist-tab [data-watch-return].no-rec-v55{font-size:12px;color:#8b95a1}
      @media(max-width:720px){
        #home-watchlist-v30 .home-watchlist-v30-chips{grid-template-columns:repeat(2,minmax(0,1fr))!important}
        #home-watchlist-v30 [data-home-watch-open]{min-width:0!important}
      }
    `;
    document.head.appendChild(style);
  }

  function setBaseline(node, symbol, perf) {
    if (!node) return;
    let baseline = node.querySelector('.watch-rec-baseline-v55');
    if (!baseline) {
      baseline = document.createElement('small');
      baseline.className = 'watch-rec-baseline-v55';
      node.appendChild(baseline);
    }
    if (!perf.rec) {
      baseline.textContent = perf.current !== null ? `추천 기록 없음 · 현재 ${formatPrice(symbol, perf.current)}` : '추천 기록 없음';
      return;
    }
    baseline.textContent = `추천 ${dateLabel(perf.rec.recommendedDate)} 종가 ${formatPrice(symbol, perf.rec.recommendedPrice)} → 현재 ${formatPrice(symbol, perf.current)}`;
  }

  function applyReturnNode(node, value) {
    if (!node) return;
    node.textContent = formatReturn(value);
    node.classList.remove('up', 'down', 'flat', 'no-rec-v55');
    node.classList.add(returnClass(value));
    if (value === null) node.classList.add('no-rec-v55');
  }

  function syncHome(quotes) {
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return;
    const kicker = section.querySelector('.home-watchlist-v30-head span');
    if (kicker) kicker.textContent = 'MY STOCKS · 추천 후 수익률';
    const more = section.querySelector('[data-home-watch-all]');
    if (more) more.textContent = '더보기 →';

    const cards = [...section.querySelectorAll('[data-home-watch-open]')];
    cards.forEach((card, index) => {
      const hidden = index >= HOME_VISIBLE;
      card.hidden = hidden;
      card.style.display = hidden ? 'none' : '';
      if (hidden) return;
      const symbol = String(card.dataset.homeWatchOpen || '').toUpperCase();
      const perf = performance(symbol, quotes);
      const price = card.querySelector('[data-home-watch-price]');
      if (price) price.textContent = formatPrice(symbol, perf.current);
      applyReturnNode(card.querySelector('[data-home-watch-return]'), perf.ret);
      setBaseline(card, symbol, perf);
    });
  }

  function syncWatchlistHeader() {
    const tab = document.getElementById('watchlist-tab');
    if (!tab) return;
    const intro = tab.querySelector('.watchlist-v30-head p');
    if (intro) intro.textContent = '추천일 종가와 현재가를 같은 기준으로 비교합니다.';
    const summary = tab.querySelector('.watchlist-v33-summary');
    if (summary) summary.setAttribute('aria-label', '관심종목 요약 · 추천일 종가 대비 현재가 기준');
    const labels = summary?.querySelectorAll('div > span') || [];
    if (labels[1]) labels[1].textContent = '추천 후 상승';
    if (labels[2]) labels[2].textContent = '추천 후 하락';
    tab.querySelectorAll('[data-watch-sort="return-desc"],[data-watch-sort="return-asc"]').forEach((button) => {
      button.textContent = button.dataset.watchSort === 'return-desc' ? '추천 수익률↑' : '추천 수익률↓';
    });
    const footer = tab.querySelector('.watchlist-v30-footer-note');
    if (footer) footer.textContent = '수익률은 ChartView 추천일 종가 대비 현재가 기준입니다. 추천 이력이 없는 종목은 수익률을 표시하지 않습니다.';
  }

  function syncWatchlistCards(quotes) {
    const tab = document.getElementById('watchlist-tab');
    if (!tab) return;
    const rows = [...tab.querySelectorAll('[data-watch-card]')];
    let up = 0, down = 0;
    for (const card of rows) {
      const symbol = String(card.dataset.watchCard || '').toUpperCase();
      const perf = performance(symbol, quotes);
      if (perf.ret !== null) {
        if (perf.ret > 0) up += 1;
        else if (perf.ret < 0) down += 1;
      }
      const price = card.querySelector('[data-watch-price]');
      if (price) price.textContent = formatPrice(symbol, perf.current);
      applyReturnNode(card.querySelector('[data-watch-return]'), perf.ret);
      const meta = card.querySelector('.watchlist-v30-meta');
      if (meta) {
        meta.textContent = perf.rec
          ? `추천 ${dateLabel(perf.rec.recommendedDate)} 종가 ${formatPrice(symbol, perf.rec.recommendedPrice)} → 현재 ${formatPrice(symbol, perf.current)}`
          : `추천 기록 없음${perf.current !== null ? ` · 현재 ${formatPrice(symbol, perf.current)}` : ''}`;
      }
    }
    const upNode = tab.querySelector('[data-watch-summary-up]');
    const downNode = tab.querySelector('[data-watch-summary-down]');
    if (upNode) upNode.textContent = String(up);
    if (downNode) downNode.textContent = String(down);

    const activeSort = tab.querySelector('[data-watch-sort].active')?.dataset.watchSort;
    if ((activeSort === 'return-desc' || activeSort === 'return-asc') && rows.length) {
      const grid = document.getElementById('watchlist-v30-grid');
      const direction = activeSort === 'return-desc' ? -1 : 1;
      rows.sort((a, b) => {
        const av = performance(String(a.dataset.watchCard || '').toUpperCase(), quotes).ret;
        const bv = performance(String(b.dataset.watchCard || '').toUpperCase(), quotes).ret;
        if (av === null && bv === null) return 0;
        if (av === null) return 1;
        if (bv === null) return -1;
        return (av - bv) * direction;
      }).forEach((row) => grid?.appendChild(row));
    }
  }

  function syncPicks() {
    document.querySelectorAll('#ai-daily-section .ai-daily-rank').forEach((rank) => rank.remove());
  }

  function sync() {
    queued = false;
    ensureStyle();
    const quotes = quoteMap();
    syncHome(quotes);
    syncWatchlistHeader();
    syncWatchlistCards(quotes);
    syncPicks();
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(sync);
  }

  function boot() {
    ensureStyle();
    loadRecommendations();
    schedule();
    if (typeof MutationObserver !== 'undefined') {
      observer = new MutationObserver(schedule);
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    document.addEventListener('chartview:watchlist-change', schedule);
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn,.watchlist-v33-refresh,[data-watch-sort]')) setTimeout(schedule, 120);
    }, true);
    setInterval(schedule, 30000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
