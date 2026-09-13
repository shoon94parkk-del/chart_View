(() => {
  'use strict';

  if (window.__chartViewNewsStatusV401Installed) return;
  window.__chartViewNewsStatusV401Installed = true;

  function syncNewsStatus() {
    const section = document.getElementById('home-personal-news-v37');
    const details = section?.querySelector('[data-news-v40-groups]');
    if (!details) return;

    const hasFailure = Boolean(details.querySelector('.news-v40-group.error'));
    const statusText = section.querySelector('[data-news-v40-status]')?.textContent || '';
    const partialFailure = hasFailure || /부분 실패|연결할 수 없습니다|불러오지 못했습니다/.test(statusText);

    if (partialFailure) {
      details.open = true;
      details.dataset.autoOpenedForFailure = '1';
    } else if (details.dataset.autoOpenedForFailure === '1') {
      details.open = false;
      delete details.dataset.autoOpenedForFailure;
    }
  }

  let scheduled = false;
  function scheduleSync() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      syncNewsStatus();
    });
  }

  document.addEventListener('chartview:v37-news-rendered', scheduleSync);

  const observer = new MutationObserver(scheduleSync);
  function boot(attempt = 0) {
    const section = document.getElementById('home-personal-news-v37');
    if (!section) {
      if (attempt < 120) setTimeout(() => boot(attempt + 1), 250);
      return;
    }
    observer.disconnect();
    observer.observe(section, { childList: true, subtree: true, characterData: true });
    syncNewsStatus();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), { once: true });
  else boot();
})();