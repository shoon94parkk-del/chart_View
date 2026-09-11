(() => {
  'use strict';

  function selectedCount() {
    const tags = document.getElementById('ticker-tags');
    if (!tags) return 0;
    return tags.querySelectorAll('.ticker-tag').length;
  }

  function updateSelectionStatus() {
    const status = document.getElementById('app-selection-status');
    if (!status) return;
    status.textContent = `선택 ${selectedCount()}/6`;
  }

  function enhanceUtilityHeader() {
    const header = document.querySelector('.header');
    const search = document.querySelector('#global-filter .global-search') || document.querySelector('.header .global-search');
    if (!header || !search || header.dataset.utilityReady === '1') return false;

    header.dataset.utilityReady = '1';
    header.classList.add('app-utility-header');
    header.querySelector('.title')?.remove();

    const top = document.createElement('div');
    top.className = 'app-utility-top';
    top.innerHTML = `
      <div class="app-utility-copy">
        <strong>종목 검색</strong>
        <span>검색한 종목을 차트 · 밸류 · 투자판단에서 함께 봅니다</span>
      </div>
      <span id="app-selection-status" class="app-selection-status">선택 0/6</span>`;
    header.appendChild(top);
    header.appendChild(search);
    search.classList.add('app-header-search');

    const label = search.querySelector('.search-label');
    if (label) label.hidden = true;

    const hint = search.querySelector('.search-hint');
    if (hint) hint.textContent = '한국 종목 · 6자리 코드 · 해외 티커 · 최대 6종목';

    const input = search.querySelector('#unified-input');
    if (input) input.placeholder = '종목명 · JYP · 005930 · AAPL';

    const tags = document.getElementById('ticker-tags');
    if (tags) {
      const observer = new MutationObserver(updateSelectionStatus);
      observer.observe(tags, { childList: true, subtree: true });
    }
    updateSelectionStatus();
    return true;
  }

  function init() {
    if (enhanceUtilityHeader()) return;
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (enhanceUtilityHeader() || attempts >= 20) clearInterval(timer);
    }, 100);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
