(() => {
  'use strict';
  if (window.__chartViewNewsReadabilityV412Installed) return;
  window.__chartViewNewsReadabilityV412Installed = true;

  function cleanTitle(title) {
    return String(title || '').replace(/\s+/g, ' ').trim();
  }

  function eventType(title) {
    const t = cleanTitle(title).toLowerCase();
    if (/실적|영업이익|매출|earnings|revenue|guidance/.test(t)) return '실적·가이던스';
    if (/수주|계약|공급|contract|deal|order/.test(t)) return '계약·수주';
    if (/인수|합병|acqui|merger/.test(t)) return '인수·합병';
    if (/배당|자사주|buyback|dividend/.test(t)) return '주주환원';
    if (/승인|fda|규제|sec|소송|lawsuit|리콜|recall/.test(t)) return '규제·법률';
    if (/목표가|투자의견|upgrade|downgrade|forecast/.test(t)) return '시장 의견';
    if (/출시|공개|신제품|서비스|launch|release|unveil/.test(t)) return '제품·서비스';
    if (/모집|교육|인재|장학|학교|청년|학생/.test(t)) return '교육·인재';
    if (/개최|행사|캠페인|festival|event/.test(t)) return '행사·브랜드';
    return '기업 동향';
  }

  function oneLineSummary(title) {
    const raw = cleanTitle(title);
    if (!raw) return '관심종목과 관련된 최신 소식입니다.';
    const withoutCompany = raw.replace(/^[^,]{1,28},\s*/, '').trim();
    const patterns = [
      [/^(.*) 모집 시작$/, (_, x) => `${x} 모집을 시작했다는 소식입니다.`],
      [/^(.*) 시작$/, (_, x) => `${x}을 시작했다는 소식입니다.`],
      [/^(.*) 개최$/, (_, x) => `${x}를 개최한다는 소식입니다.`],
      [/^(.*) 발표$/, (_, x) => `${x}를 발표했다는 소식입니다.`],
      [/^(.*) 출시$/, (_, x) => `${x}를 출시했다는 소식입니다.`],
      [/^(.*) 공개$/, (_, x) => `${x}를 공개했다는 소식입니다.`],
    ];
    for (const [pattern, make] of patterns) {
      const match = withoutCompany.match(pattern);
      if (match) return make(...match);
    }
    const type = eventType(raw);
    const core = withoutCompany.length > 72 ? `${withoutCompany.slice(0, 69)}…` : withoutCompany;
    return `${type} 관련 소식으로, 제목 기준 핵심은 “${core}”입니다.`;
  }

  function addSummary(card) {
    if (!card || card.querySelector(':scope > .news-v412-summary, .news-v412-summary')) return;
    const title = card.querySelector('h4');
    if (!title) return;
    const box = document.createElement('p');
    box.className = 'news-v412-summary';
    box.innerHTML = `<b>한줄 요약 <small>제목 기준</small></b><span></span>`;
    box.querySelector('span').textContent = oneLineSummary(title.textContent);
    title.insertAdjacentElement('afterend', box);
  }

  function parseSpark(svg) {
    const points = svg?.querySelector('polyline')?.getAttribute('points') || '';
    const rows = points.split(/\s+/).map((pair) => pair.split(',').map(Number)).filter((p) => p.length === 2 && p.every(Number.isFinite));
    if (rows.length < 2) return null;
    const ys = rows.map((p) => p[1]);
    const minY = Math.min(...ys), maxY = Math.max(...ys), span = maxY - minY || 1;
    const last = ys.at(-1), prev = ys.at(-2);
    const recentMove = prev - last;
    const recent = Math.abs(recentMove) < span * 0.06 ? '최근 2거래일 횡보' : recentMove > 0 ? '최근 2거래일 반등' : '최근 2거래일 약세';
    const position = (last - minY) / span;
    const zone = position <= 0.2 ? '기간 고점권' : position >= 0.8 ? '기간 저점권' : '기간 중간권';
    return { recent, zone };
  }

  function enhanceMarket(details) {
    if (!details) return;
    details.open = true;
    const target = details.querySelector('[data-news-v40-market]');
    const svg = target?.querySelector('svg');
    const pctNode = target?.querySelector('strong');
    if (!target || !svg || !pctNode) return;
    const shape = parseSpark(svg);
    if (!shape) return;
    const pct = cleanTitle(pctNode.textContent) || '5D 변동률 확인 중';
    let metrics = target.querySelector('.news-v412-market-metrics');
    if (!metrics) {
      metrics = document.createElement('div');
      metrics.className = 'news-v412-market-metrics';
      target.insertBefore(metrics, target.firstChild);
    }
    metrics.innerHTML = '<strong></strong><span></span>';
    metrics.querySelector('strong').textContent = `5D ${pct}`;
    metrics.querySelector('span').textContent = `${shape.recent} · ${shape.zone}`;
    if (!target.querySelector('.news-v412-chart-axis')) {
      const axis = document.createElement('div');
      axis.className = 'news-v412-chart-axis';
      axis.innerHTML = '<span>5거래일 전</span><span>현재</span>';
      target.appendChild(axis);
    }
    target.classList.add('news-v412-market-ready');
  }

  function enhanceAll() {
    document.querySelectorAll('.news-v40-card').forEach((card) => {
      addSummary(card);
      enhanceMarket(card.querySelector('.news-v40-market'));
    });
    document.querySelectorAll('.my-hub-v41-news-row').forEach(addSummary);
    const home = document.querySelector('#home-tab .home-v8');
    if (home) home.dataset.newsReadability = 'v41.2';
    const hub = document.getElementById('watchlist-tab');
    if (hub) hub.dataset.newsReadability = 'v41.2';
  }

  let queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; enhanceAll(); });
  }

  const observer = new MutationObserver(schedule);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  document.addEventListener('chartview:v37-news-rendered', schedule);
  document.addEventListener('DOMContentLoaded', schedule, { once: true });
  schedule();
})();
