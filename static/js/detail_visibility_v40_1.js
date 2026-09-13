(() => {
  'use strict';

  if (window.__chartViewDetailVisibilityV401Installed) return;
  window.__chartViewDetailVisibilityV401Installed = true;

  let scheduled = false;
  let repairing = false;

  function detailIsOpen() {
    return Boolean(window.ChartViewState?.detail?.open);
  }

  function repairVisibility() {
    scheduled = false;
    if (repairing || !detailIsOpen()) return;

    const section = document.getElementById('stock-detail-v40');
    const chartTab = document.getElementById('chart-tab');
    if (!section || !chartTab) return;

    const tabVisible = chartTab.classList.contains('active') && !chartTab.hidden;
    const sectionVisible = !section.hidden;
    if (tabVisible && sectionVisible) return;

    repairing = true;
    try {
      // ChartViewState is the V40 source of truth. Legacy tab initialization can
      // finish after openDetail() and accidentally return the app to Home.
      if (!tabVisible) {
        if (typeof window.__openAppTab === 'function') {
          window.__openAppTab('chart', { history: false });
        } else if (typeof window.switchTab === 'function') {
          window.switchTab('chart');
        } else {
          document.querySelectorAll('.tab-content').forEach((node) => node.classList.remove('active'));
          chartTab.classList.add('active');
          chartTab.hidden = false;
        }
      }
      if (detailIsOpen()) {
        section.hidden = false;
        document.body.classList.add('app-detail-v40-open');
      }
    } finally {
      queueMicrotask(() => { repairing = false; });
    }
  }

  function scheduleRepair() {
    if (scheduled || !detailIsOpen()) return;
    scheduled = true;
    requestAnimationFrame(repairVisibility);
  }

  const observer = new MutationObserver(scheduleRepair);

  function boot() {
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'hidden']
    });
    document.addEventListener('chartview:detail-change', scheduleRepair);
    window.addEventListener('popstate', scheduleRepair);
    setTimeout(scheduleRepair, 0);
    setTimeout(scheduleRepair, 250);
    setTimeout(scheduleRepair, 1200);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
