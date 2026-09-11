(() => {
  'use strict';

  function enhanceMarket() {
    const panel = document.getElementById('home-market-v9');
    const grid = document.getElementById('home-market-v9-grid');
    if (!panel || !grid) return false;

    const items = Array.from(grid.querySelectorAll('.home-market-v9-item'));
    if (items.length < 4) return false;

    items.forEach((item, index) => {
      item.classList.toggle('home23-primary', index < 4);
      item.classList.toggle('home23-secondary', index >= 4);
    });

    let toggle = panel.querySelector('[data-home23-market-toggle]');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'home23-market-toggle';
      toggle.dataset.home23MarketToggle = '1';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.innerHTML = '<span>금리 · VIX · 유가 · 환율</span><strong>4개 더보기</strong><i>⌄</i>';
      grid.insertAdjacentElement('afterend', toggle);

      // Pure UI toggle: no fetch, no home re-render, no observer.
      toggle.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const expanded = !panel.classList.contains('home23-expanded');
        panel.classList.toggle('home23-expanded', expanded);
        toggle.setAttribute('aria-expanded', String(expanded));
        const strong = toggle.querySelector('strong');
        if (strong) strong.textContent = expanded ? '접기' : '4개 더보기';
      });
    }

    panel.dataset.home23 = '1';
    return true;
  }

  function compactDataStatus() {
    const status = document.getElementById('ux12-data-status');
    const home = document.querySelector('#home-tab .home-v8');
    if (!status || !home) return false;

    status.classList.add('home23-data-status');
    const head = status.querySelector('.ux12-status-head strong');
    if (head) head.textContent = '데이터 기준';
    const body = document.getElementById('home-v8-body');
    if (body && status.previousElementSibling !== body) body.insertAdjacentElement('afterend', status);
    return true;
  }

  function enforceOrder() {
    const home = document.querySelector('#home-tab .home-v8');
    const market = document.getElementById('home-market-v9');
    const body = document.getElementById('home-v8-body');
    if (!home || !market || !body) return false;
    if (home.firstElementChild !== market) home.insertBefore(market, home.firstElementChild);
    compactDataStatus();
    return true;
  }

  function stabilizeHome() {
    enhanceMarket();
    enforceOrder();
  }

  function boot() {
    // Mobile stability: a few scheduled idempotent passes, never a rapid interval.
    requestAnimationFrame(stabilizeHome);
    setTimeout(stabilizeHome, 400);
    setTimeout(stabilizeHome, 1200);

    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) {
        setTimeout(stabilizeHome, 100);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();