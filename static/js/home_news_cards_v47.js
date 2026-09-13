(() => {
  'use strict';
  if (window.__chartViewHomeNewsCardsV47Installed) return;
  window.__chartViewHomeNewsCardsV47Installed = true;

  let queued = false;
  let observer = null;

  function enhance() {
    const section = document.getElementById('home-personal-news-v37');
    if (!section) return false;
    const cards = [...section.querySelectorAll('.news-v40-card')].slice(0, 3);
    cards.forEach((card, index) => {
      const rank = String(index + 1);
      if (card.dataset.homeNewsRank !== rank) card.dataset.homeNewsRank = rank;
      const details = card.querySelector('.news-v40-market');
      if (details) {
        if (!details.open) details.open = true;
        if (details.dataset.v47AlwaysOpen !== '1') details.dataset.v47AlwaysOpen = '1';
        const summary = details.querySelector('summary');
        if (summary) {
          if (summary.textContent !== '5거래일 가격 흐름') summary.textContent = '5거래일 가격 흐름';
          if (summary.getAttribute('aria-label') !== '5거래일 가격 흐름') summary.setAttribute('aria-label', '5거래일 가격 흐름');
        }
      }
    });
    if (section.dataset.newsCards !== 'v47') section.dataset.newsCards = 'v47';
    return true;
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      enhance();
    });
  }

  function attach(attempt = 0) {
    const section = document.getElementById('home-personal-news-v37');
    if (!section) {
      if (attempt < 40) setTimeout(() => attach(attempt + 1), 250);
      return;
    }
    if (!observer) {
      observer = new MutationObserver(schedule);
      observer.observe(section, { childList: true, subtree: true });
    }
    schedule();
  }

  document.addEventListener('chartview:v37-news-rendered', schedule);
  document.addEventListener('chartview:watchlist-change', schedule);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => attach(), { once: true });
  else attach();
})();
