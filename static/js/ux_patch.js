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
