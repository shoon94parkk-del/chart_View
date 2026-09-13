(() => {
  'use strict';
  if (window.__chartViewDetailVisibilityV401Installed) return;
  window.__chartViewDetailVisibilityV401Installed = true;

  let scheduled = false;
  let repairing = false;
  let targetObserver = null;
  let bindTimer = null;

  function detailIsCurrent() {
    if (!window.ChartViewState?.detail?.open) return false;
    const state = history.state || {};
    return !state.chartView || state.view === 'detail';
  }

  function repairVisibility() {
    scheduled = false;
    if (repairing || !detailIsCurrent()) return;
    const section = document.getElementById('stock-detail-v40');
    const chartTab = document.getElementById('chart-tab');
    if (!section || !chartTab) return;
    const tabVisible = chartTab.classList.contains('active') && !chartTab.hidden;
    const sectionVisible = !section.hidden;
    if (tabVisible && sectionVisible) return;

    repairing = true;
    try {
      if (!tabVisible && detailIsCurrent()) {
        if (typeof window.__openAppTab === 'function') window.__openAppTab('chart', { history: false });
        else if (typeof window.switchTab === 'function') window.switchTab('chart');
      }
      if (detailIsCurrent()) {
        section.hidden = false;
        document.body.classList.add('app-detail-v40-open');
      }
    } finally {
      queueMicrotask(() => { repairing = false; });
    }
  }

  function scheduleRepair() {
    if (scheduled || !detailIsCurrent()) return;
    scheduled = true;
    requestAnimationFrame(repairVisibility);
  }

  function bindTargets(attempt = 0) {
    clearTimeout(bindTimer);
    targetObserver?.disconnect();
    const chartTab = document.getElementById('chart-tab');
    const section = document.getElementById('stock-detail-v40');
    const targets = [chartTab, section].filter(Boolean);
    if (targets.length) {
      targetObserver = new MutationObserver(scheduleRepair);
      targets.forEach((node) => targetObserver.observe(node, { attributes: true, attributeFilter: ['class', 'hidden'] }));
    }
    if ((!chartTab || !section) && attempt < 20) bindTimer = setTimeout(() => bindTargets(attempt + 1), 250);
    scheduleRepair();
  }

  document.addEventListener('chartview:detail-change', (event) => {
    if (event.detail?.open) bindTargets();
    else { scheduled = false; targetObserver?.disconnect(); }
  });
  window.addEventListener('popstate', () => requestAnimationFrame(scheduleRepair));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => bindTargets(), { once: true });
  else bindTargets();
})();
