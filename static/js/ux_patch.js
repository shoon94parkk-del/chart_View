// Load the fast screener without changing the original template file.
(() => {
  if (!document.querySelector('link[data-fast-screener]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/css/screener.css?v=20260910v1';
    link.dataset.fastScreener = '1';
    document.head.appendChild(link);
  }
  if (!document.querySelector('script[data-fast-screener]')) {
    const script = document.createElement('script');
    script.src = '/static/js/screener.js?v=20260910v1';
    script.dataset.fastScreener = '1';
    document.head.appendChild(script);
  }
})();

document.addEventListener('DOMContentLoaded', () => {
  const sector = document.querySelector('.sector-section');
  if (sector && !sector.querySelector('.ux-sector-toggle')) {
    const toggle = document.createElement('button');
    toggle.className = 'ux-sector-toggle';
    toggle.type = 'button';
    toggle.innerHTML = '<span>추천 종목</span><span class="ux-sector-arrow">펼치기 ↓</span>';
    sector.insertBefore(toggle, sector.firstChild);
    sector.classList.add('ux-collapsed');
    toggle.addEventListener('click', () => {
      const collapsed = sector.classList.toggle('ux-collapsed');
      toggle.querySelector('.ux-sector-arrow').textContent = collapsed ? '펼치기 ↓' : '접기 ↑';
    });
  }

  const chartHeader = document.querySelector('.chart-header');
  if (chartHeader && !document.querySelector('.ux-data-status')) {
    const status = document.createElement('div');
    status.className = 'ux-data-status';
    status.textContent = '시세: Yahoo Finance · 국내 종목 검색: KRX · 한국 시세는 지연될 수 있습니다.';
    chartHeader.insertAdjacentElement('afterend', status);
  }

  const input = document.getElementById('unified-input');
  if (input) input.setAttribute('aria-label', '종목명, 6자리 종목코드 또는 해외 티커 검색');
});
