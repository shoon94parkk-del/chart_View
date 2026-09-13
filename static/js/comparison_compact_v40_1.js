(() => {
  'use strict';

  if (window.__chartViewComparisonCompactV401Installed) return;
  window.__chartViewComparisonCompactV401Installed = true;

  const DESKTOP = '(min-width: 721px)';

  function install() {
    const section = document.querySelector('#global-filter .sector-section');
    const content = section?.querySelector('.sector-scroll-container');
    if (!section || !content) return false;

    let button = section.querySelector('[data-v40-sector-toggle]');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'v40-sector-toggle';
      button.dataset.v40SectorToggle = '1';
      button.setAttribute('aria-controls', 'v40-sector-picks');
      content.id ||= 'v40-sector-picks';
      section.insertBefore(button, content);
      button.addEventListener('click', () => {
        const collapsed = section.dataset.v40Collapsed !== 'false';
        section.dataset.v40Collapsed = collapsed ? 'false' : 'true';
        sync(section, button, content);
      });
    }

    if (!section.dataset.v40DesktopInitialized && matchMedia(DESKTOP).matches) {
      section.dataset.v40Collapsed = 'true';
      section.dataset.v40DesktopInitialized = '1';
    }
    sync(section, button, content);
    return true;
  }

  function sync(section, button, content) {
    const desktop = matchMedia(DESKTOP).matches;
    const collapsed = desktop && section.dataset.v40Collapsed !== 'false';
    section.classList.toggle('v40-sector-collapsed', collapsed);
    button.hidden = !desktop;
    button.setAttribute('aria-expanded', String(!collapsed));
    button.textContent = collapsed ? '빠른 종목 추가 펼치기' : '빠른 종목 추가 접기';
    content.setAttribute('aria-hidden', String(collapsed));
  }

  function boot(attempt = 0) {
    if (!install() && attempt < 80) setTimeout(() => boot(attempt + 1), 250);
  }

  matchMedia(DESKTOP).addEventListener?.('change', () => install());
  document.addEventListener('chartview:compare-change', () => setTimeout(install, 0));

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), { once: true });
  else boot();
})();