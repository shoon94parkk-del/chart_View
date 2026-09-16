/* ChartView UI continuity v53: naming and semantics only; feature logic stays in existing modules. */
(() => {
  'use strict';

  let attempts = 0;
  let queued = false;

  function ensurePickOrigin(head) {
    if (!head || head.querySelector('.cv-pick-origin')) return;
    const eyebrow = head.querySelector('.ai-ledger-eyebrow');
    if (!eyebrow) return;
    const origin = document.createElement('span');
    origin.className = 'cv-pick-origin';
    origin.textContent = 'AI 스크리닝 · 최종 선정';
    eyebrow.insertAdjacentElement('afterend', origin);
  }

  function syncPickNaming() {
    const homeTitle = document.querySelector('#ai-daily-section .ai-daily-head h2');
    if (homeTitle && homeTitle.textContent !== 'ChartView PICK 3') homeTitle.textContent = 'ChartView PICK 3';

    const homeMeta = document.querySelector('#ai-daily-section .ai-daily-head p');
    if (homeMeta && !homeMeta.dataset.cvPickMeta) {
      const date = (homeMeta.textContent || '').split('·')[0].trim();
      homeMeta.textContent = `${date} · AI 스크리닝 · 최종 선정`;
      homeMeta.dataset.cvPickMeta = '1';
    }

    const pickTab = document.querySelector('[data-discovery-view="ai-picks"]');
    if (pickTab && pickTab.textContent !== 'PICK 기록') pickTab.textContent = 'PICK 기록';

    const pickPanel = document.querySelector('[data-discovery-panel="ai-picks"]');
    if (pickPanel) pickPanel.setAttribute('aria-label', 'ChartView PICK 누적 기록');

    const eyebrow = document.querySelector('.ai-ledger-eyebrow');
    if (eyebrow && eyebrow.textContent !== 'CHARTVIEW PICK') eyebrow.textContent = 'CHARTVIEW PICK';

    const ledgerHead = document.querySelector('.ai-ledger-head');
    if (ledgerHead) {
      ensurePickOrigin(ledgerHead);
      const desc = ledgerHead.querySelector('p');
      if (desc && !desc.dataset.cvPickDesc) {
        desc.textContent = 'AI가 후보를 스크리닝하고 사람이 최종 선정한 종목의 성과를 한 화면에서 누적 비교합니다.';
        desc.dataset.cvPickDesc = '1';
      }
    }

    const kpis = document.querySelector('[data-ledger-kpis]');
    if (kpis) kpis.setAttribute('aria-label', 'PICK 성과 요약');
    const tools = document.querySelector('.ai-ledger-tools');
    if (tools) tools.setAttribute('aria-label', 'PICK 기록 필터');
  }

  function syncSurfaceSemantics() {
    document.body?.classList.add('cv-ui-continuity-v53');
    const revision = document.querySelector('.revision-gap-panel');
    if (revision) revision.dataset.cvUnifiedSurface = '1';
    const ledger = document.querySelector('.ai-ledger-panel');
    if (ledger) ledger.dataset.cvUnifiedSurface = '1';
  }

  function sync() {
    queued = false;
    syncPickNaming();
    syncSurfaceSemantics();
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(sync);
  }

  function init() {
    sync();
    const timer = setInterval(() => {
      sync();
      attempts += 1;
      if (attempts >= 50) clearInterval(timer);
    }, 200);
    document.addEventListener('click', schedule, true);
    document.addEventListener('chartview:v37-news-rendered', schedule);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
