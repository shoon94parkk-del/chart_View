(() => {
  'use strict';

  const HOME_WATCHLIST_VISIBLE = 4;
  let queued = false;

  function compactHomeWatchlist() {
    const section = document.getElementById('home-watchlist-v30');
    if (!section) return false;

    const cards = [...section.querySelectorAll('[data-home-watch-open]')];
    cards.forEach((card, index) => {
      const hidden = index >= HOME_WATCHLIST_VISIBLE;
      card.hidden = hidden;
      card.setAttribute('aria-hidden', hidden ? 'true' : 'false');
      if (hidden) card.style.display = 'none';
      else card.style.removeProperty('display');
    });

    const more = section.querySelector('[data-home-watch-all]');
    if (more) {
      more.textContent = '더보기 →';
      more.setAttribute('aria-label', '관심종목 전체보기');
    }
    return true;
  }

  function equalizeHomePicks() {
    const section = document.getElementById('ai-daily-section');
    if (!section) return false;
    section.querySelectorAll('.ai-daily-rank').forEach((rank) => rank.remove());
    return true;
  }

  function installStyle() {
    if (document.getElementById('home-summary-v54-style')) return;
    const style = document.createElement('style');
    style.id = 'home-summary-v54-style';
    style.textContent = `
      #home-tab .ai-daily-card summary{
        grid-template-areas:'name score' 'price arrow' !important;
      }
      @media(max-width:700px){
        #home-tab .ai-daily-card summary{
          grid-template-areas:'name score arrow' 'price score arrow' !important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function sync() {
    queued = false;
    installStyle();
    compactHomeWatchlist();
    equalizeHomePicks();
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(sync);
  }

  function boot() {
    sync();
    const home = document.getElementById('home-tab');
    if (home && typeof MutationObserver !== 'undefined') {
      new MutationObserver(schedule).observe(home, { childList: true, subtree: true });
    }
    document.addEventListener('chartview:watchlist-change', schedule);
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(schedule, 50);
    }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
