(() => {
  'use strict';

  const CANONICAL = 'https://chart-view-bsg6.onrender.com/';
  const TITLE = 'Chart View | 한국·미국 주식 차트·밸류에이션 비교';
  const DESCRIPTION = '한국·미국 주식 최대 6종목의 수익률 차트, 밸류에이션, 투자판단 근거와 시장 지표를 로그인 없이 한 화면에서 비교합니다.';
  const SHARE_TEXT = '한국·미국 주식을 차트와 밸류에이션으로 한 번에 비교할 수 있는 무료 웹앱 Chart View';
  const SEEN_KEY = 'chartview-promo-v1-seen';

  function upsertMeta(selector, attrs) {
    let node = document.head.querySelector(selector);
    if (!node) {
      node = document.createElement('meta');
      document.head.appendChild(node);
    }
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function upsertLink(selector, attrs) {
    let node = document.head.querySelector(selector);
    if (!node) {
      node = document.createElement('link');
      document.head.appendChild(node);
    }
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function hydrateHead() {
    document.title = TITLE;
    upsertMeta('meta[name="description"]', { name: 'description', content: DESCRIPTION });
    upsertMeta('meta[name="robots"]', { name: 'robots', content: 'index,follow,max-image-preview:large' });
    upsertMeta('meta[property="og:type"]', { property: 'og:type', content: 'website' });
    upsertMeta('meta[property="og:locale"]', { property: 'og:locale', content: 'ko_KR' });
    upsertMeta('meta[property="og:site_name"]', { property: 'og:site_name', content: 'Chart View' });
    upsertMeta('meta[property="og:title"]', { property: 'og:title', content: TITLE });
    upsertMeta('meta[property="og:description"]', { property: 'og:description', content: DESCRIPTION });
    upsertMeta('meta[property="og:url"]', { property: 'og:url', content: CANONICAL });
    upsertMeta('meta[property="og:image"]', { property: 'og:image', content: `${CANONICAL}static/social-card.svg` });
    upsertMeta('meta[name="twitter:card"]', { name: 'twitter:card', content: 'summary_large_image' });
    upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: TITLE });
    upsertMeta('meta[name="twitter:description"]', { name: 'twitter:description', content: DESCRIPTION });
    upsertMeta('meta[name="twitter:image"]', { name: 'twitter:image', content: `${CANONICAL}static/social-card.svg` });
    upsertLink('link[rel="canonical"]', { rel: 'canonical', href: CANONICAL });
    upsertLink('link[rel="icon"]', { rel: 'icon', type: 'image/svg+xml', href: '/static/chartview-mark.svg' });
  }

  function loadAiDailyWidget() {
    const existing = document.querySelector('script[data-ai-daily-home]');
    if (existing) {
      if (existing.dataset.version !== 'v5') existing.remove();
      else {
        if (typeof window.__ensureAiDailyTop3 === 'function') window.__ensureAiDailyTop3();
        return;
      }
    }
    const script = document.createElement('script');
    script.src = '/static/js/ai_daily_widget.js?v=20260914v5';
    script.async = false;
    script.dataset.aiDailyHome = '1';
    script.dataset.version = 'v5';
    document.head.appendChild(script);
  }

  function trackedShareUrl() {
    const url = new URL(CANONICAL);
    url.searchParams.set('utm_source', 'share');
    url.searchParams.set('utm_medium', 'web');
    url.searchParams.set('utm_campaign', 'chartview_v1');
    return url.toString();
  }

  function toast(message) {
    document.querySelector('.promo-v1-toast')?.remove();
    const node = document.createElement('div');
    node.className = 'promo-v1-toast';
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 1800);
  }

  async function shareChartView() {
    const url = trackedShareUrl();
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Chart View', text: SHARE_TEXT, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      toast('Chart View 링크를 복사했습니다.');
    } catch (error) {
      if (error?.name === 'AbortError') return;
      try {
        const input = document.createElement('textarea');
        input.value = url;
        input.setAttribute('readonly', '');
        input.style.position = 'fixed';
        input.style.opacity = '0';
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        input.remove();
        toast('Chart View 링크를 복사했습니다.');
      } catch (_) {
        toast('주소창의 링크를 복사해 공유해주세요.');
      }
    }
  }

  function markSeen() {
    try { sessionStorage.setItem(SEEN_KEY, '1'); } catch (_) { }
  }

  function shouldShowIntro() {
    const params = new URLSearchParams(window.location.search);
    const campaign = params.get('utm_campaign') || '';
    const launchVisit = campaign === 'launch_v1' || campaign === 'chartview_v1' || params.get('welcome') === '1';
    if (!launchVisit) return false;
    try {
      if (sessionStorage.getItem(SEEN_KEY) === '1') return false;
    } catch (_) { }
    return true;
  }

  function focusSearch() {
    markSeen();
    document.querySelector('.promo-v1-intro')?.remove();
    const input = document.getElementById('unified-input');
    if (input) {
      input.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => input.focus({ preventScroll: true }), 350);
      return;
    }
    const home = document.querySelector('.app-bottom-btn[data-app-mode="home"]');
    home?.click();
  }

  function mountIntro() {
    if (!shouldShowIntro() || document.querySelector('.promo-v1-intro')) return;
    const anchor = document.getElementById('global-filter') || document.querySelector('.tab-nav') || document.getElementById('app')?.firstElementChild;
    if (!anchor?.parentNode) return;

    const section = document.createElement('section');
    section.className = 'promo-v1-intro';
    section.setAttribute('aria-label', 'Chart View 소개');
    section.innerHTML = `
      <button type="button" class="promo-v1-close" aria-label="소개 닫기">×</button>
      <div class="promo-v1-kicker">PUBLIC BETA · 무료</div>
      <h2 class="promo-v1-title">한국·미국 주식, 차트부터 밸류에이션까지 한 화면에서</h2>
      <p class="promo-v1-copy">최대 6종목을 동시에 비교하고, 수익률·FWD PER·PER·ROE·시장 흐름과 투자판단 근거를 빠르게 확인하세요.</p>
      <div class="promo-v1-points" aria-label="주요 특징">
        <span class="promo-v1-point">로그인 불필요</span>
        <span class="promo-v1-point">한국·미국 종목</span>
        <span class="promo-v1-point">모바일 최적화</span>
        <span class="promo-v1-point">투자 참고용</span>
      </div>
      <div class="promo-v1-actions">
        <button type="button" class="promo-v1-action primary" data-promo-start>종목 비교 시작</button>
        <button type="button" class="promo-v1-action" data-promo-share>친구에게 공유</button>
      </div>`;
    anchor.parentNode.insertBefore(section, anchor);
    section.querySelector('.promo-v1-close')?.addEventListener('click', () => { markSeen(); section.remove(); });
    section.querySelector('[data-promo-start]')?.addEventListener('click', focusSearch);
    section.querySelector('[data-promo-share]')?.addEventListener('click', shareChartView);
  }

  function mountFooterShare() {
    const footer = document.querySelector('.app-footer');
    if (!footer || document.querySelector('.promo-v1-footer-share')) return;
    const wrap = document.createElement('div');
    wrap.className = 'promo-v1-footer-share';
    wrap.innerHTML = '<button type="button">↗ Chart View 공유하기</button>';
    footer.parentNode.insertBefore(wrap, footer);
    wrap.querySelector('button')?.addEventListener('click', shareChartView);
  }

  function init() {
    hydrateHead();
    mountIntro();
    mountFooterShare();
    loadAiDailyWidget();
  }

  hydrateHead();
  loadAiDailyWidget();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();