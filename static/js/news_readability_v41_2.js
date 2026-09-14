(() => {
  'use strict';
  if (window.__chartViewNewsReadabilityV412Installed) return;
  window.__chartViewNewsReadabilityV412Installed = true;

  const summaryCache = new Map();
  const summaryQueue = [];
  const SUMMARY_CONCURRENCY = 3;
  let activeSummaryJobs = 0;

  function cleanTitle(title) {
    return String(title || '').replace(/\s+/g, ' ').trim();
  }

  function summaryKey(url, title, snippet) {
    return `${url}|${title}|${String(snippet || '').slice(0, 240)}`;
  }

  function pumpSummaryQueue() {
    while (activeSummaryJobs < SUMMARY_CONCURRENCY && summaryQueue.length) {
      const job = summaryQueue.shift();
      activeSummaryJobs += 1;
      const params = new URLSearchParams({ url: job.url, title: job.title });
      if (job.snippet) params.set('snippet', job.snippet.slice(0, 1100));
      fetch(`/api/news-summary?${params}`, { cache: 'default' })
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((payload) => {
          summaryCache.set(job.key, payload);
          job.resolve(payload);
        })
        .catch(job.reject)
        .finally(() => {
          activeSummaryJobs -= 1;
          pumpSummaryQueue();
        });
    }
  }

  function loadContentSummary(url, title, snippet = '') {
    const key = summaryKey(url, title, snippet);
    if (summaryCache.has(key)) return Promise.resolve(summaryCache.get(key));
    return new Promise((resolve, reject) => {
      summaryQueue.push({ key, url, title, snippet, resolve, reject });
      pumpSummaryQueue();
    });
  }

  function articleUrl(card) {
    const link = card?.querySelector('.news-v40-actions a[href], .my-hub-v41-news-actions a[href], a[target="_blank"][href]');
    return String(link?.href || '').trim();
  }

  function applyKoreanTitle(titleNode, payload, originalTitle) {
    const translated = cleanTitle(payload?.titleKo);
    if (!translated || translated === '해외 기사') return;
    titleNode.textContent = translated;
    if (translated !== originalTitle) titleNode.title = `원문 제목: ${originalTitle}`;
  }

  function setImportant(node, property, value) {
    if (node) node.style.setProperty(property, value, 'important');
  }

  function clearInlineExpansion(node, properties) {
    if (!node) return;
    properties.forEach((property) => node.style.removeProperty(property));
  }

  function syncSummaryExpansion(box, expanded) {
    const text = box?.querySelector('.news-v417-summary-text');
    const main = box?.closest('.my-hub-v41-news-main');
    const row = box?.closest('.my-hub-v41-news-row');
    const boxProps = ['height', 'max-height', 'overflow'];
    const textProps = ['display', '-webkit-box-orient', '-webkit-line-clamp', 'line-clamp', 'height', 'max-height', 'overflow', 'white-space', 'text-overflow'];
    const parentProps = ['height', 'max-height', 'overflow'];

    if (expanded) {
      setImportant(box, 'height', 'auto');
      setImportant(box, 'max-height', 'none');
      setImportant(box, 'overflow', 'visible');
      setImportant(text, 'display', 'block');
      setImportant(text, '-webkit-box-orient', 'initial');
      setImportant(text, '-webkit-line-clamp', 'unset');
      setImportant(text, 'line-clamp', 'unset');
      setImportant(text, 'height', 'auto');
      setImportant(text, 'max-height', 'none');
      setImportant(text, 'overflow', 'visible');
      setImportant(text, 'white-space', 'normal');
      setImportant(text, 'text-overflow', 'clip');
      [main, row].forEach((node) => {
        setImportant(node, 'height', 'auto');
        setImportant(node, 'max-height', 'none');
        setImportant(node, 'overflow', 'visible');
      });
      return;
    }

    clearInlineExpansion(box, boxProps);
    clearInlineExpansion(text, textProps);
    [main, row].forEach((node) => clearInlineExpansion(node, parentProps));
  }

  function addSummary(card) {
    if (!card || card.querySelector('.news-v412-summary')) return;
    const title = card.querySelector('h4');
    if (!title) return;
    const originalTitle = cleanTitle(title.textContent);
    const url = articleUrl(card);
    const snippet = String(card.dataset.newsSummarySeed || '').trim();

    const box = document.createElement('button');
    box.type = 'button';
    box.className = 'news-v412-summary is-loading';
    box.setAttribute('aria-expanded', 'false');
    box.setAttribute('aria-label', '본문 요약 전체보기');
    box.innerHTML = '<span class="news-v417-summary-head"><b>한줄 요약 <small>본문 확인 중</small></b><i>전체보기</i></span><span class="news-v417-summary-text">기사 본문을 읽고 한국어로 요약하고 있습니다…</span>';
    title.insertAdjacentElement('afterend', box);

    box.addEventListener('click', () => {
      const expanded = box.getAttribute('aria-expanded') === 'true';
      const nextExpanded = !expanded;
      box.setAttribute('aria-expanded', String(nextExpanded));
      box.classList.toggle('is-expanded', nextExpanded);
      box.querySelector('.news-v417-summary-head i').textContent = nextExpanded ? '접기' : '전체보기';
      box.setAttribute('aria-label', nextExpanded ? '본문 요약 접기' : '본문 요약 전체보기');
      syncSummaryExpansion(box, nextExpanded);
    });

    const label = box.querySelector('.news-v417-summary-head small');
    const text = box.querySelector('.news-v417-summary-text');
    if (!url || !originalTitle) {
      box.classList.remove('is-loading');
      box.classList.add('is-error');
      label.textContent = '본문 접근 제한';
      text.textContent = '원문 주소를 확인할 수 없어 내용 기반 요약을 제공하지 못했습니다.';
      return;
    }

    loadContentSummary(url, originalTitle, snippet)
      .then((payload) => {
        if (!box.isConnected || !title.isConnected) return;
        applyKoreanTitle(title, payload, originalTitle);
        box.classList.remove('is-loading', 'is-error');
        box.dataset.summaryBasis = payload?.basis || '';
        label.textContent = cleanTitle(payload?.basisLabel) || '본문 기반';
        text.textContent = cleanTitle(payload?.summary) || '본문 요약을 만들지 못했습니다. 원문 보기에서 확인해 주세요.';
        if (box.getAttribute('aria-expanded') === 'true') syncSummaryExpansion(box, true);
      })
      .catch(() => {
        if (!box.isConnected) return;
        box.classList.remove('is-loading');
        box.classList.add('is-error');
        label.textContent = '요약 실패';
        text.textContent = '기사 본문 요약을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
      });
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
    const target = details.querySelector('[data-news-v40-market]');
    const svg = target?.querySelector(':scope > svg');
    const pctNode = target?.querySelector(':scope > strong');
    if (!target || !svg || !pctNode) return;
    const shape = parseSpark(svg);
    if (!shape) return;
    const pct = cleanTitle(pctNode.textContent) || '변동률 확인 중';
    const signature = `${pct}|${shape.recent}|${shape.zone}`;
    let metrics = target.querySelector(':scope > .news-v412-market-metrics');
    if (!metrics) {
      metrics = document.createElement('div');
      metrics.className = 'news-v412-market-metrics';
      metrics.innerHTML = '<strong></strong><span></span>';
      target.insertBefore(metrics, target.firstChild);
    }
    if (metrics.dataset.signature !== signature) {
      metrics.dataset.signature = signature;
      metrics.querySelector('strong').textContent = `5D ${pct}`;
      metrics.querySelector('span').textContent = `${shape.recent} · ${shape.zone}`;
    }
    if (!target.querySelector(':scope > .news-v412-chart-axis')) {
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
      const details = card.querySelector('.news-v40-market');
      if (details && details.dataset.v415DefaultOpen !== '1') {
        details.dataset.v415DefaultOpen = '1';
        details.open = card.classList.contains('is-lead');
      }
      enhanceMarket(details);
    });
    document.querySelectorAll('.my-hub-v41-news-row').forEach(addSummary);
    const home = document.querySelector('#home-tab .home-v8');
    if (home) home.dataset.newsReadability = 'v49';
    const hub = document.getElementById('watchlist-tab');
    if (hub) hub.dataset.newsReadability = 'v49';
  }

  let queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; enhanceAll(); });
  }

  let newsObserver = null;
  function attachNewsObserver(attempt = 0) {
    const section = document.getElementById('home-personal-news-v37');
    if (section) {
      if (!newsObserver) {
        newsObserver = new MutationObserver(schedule);
        newsObserver.observe(section, { childList: true, subtree: true });
      }
      schedule();
      return;
    }
    if (attempt < 30) setTimeout(() => attachNewsObserver(attempt + 1), 300);
  }
  document.addEventListener('chartview:v37-news-rendered', () => { attachNewsObserver(); schedule(); });
  document.addEventListener('chartview:v41-news-rendered', schedule);
  document.addEventListener('DOMContentLoaded', () => attachNewsObserver(), { once: true });
  attachNewsObserver();
})();