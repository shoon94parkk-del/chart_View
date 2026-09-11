(() => {
  'use strict';

  const TOOLS = [
    { name: 'Finviz', short: 'FZ', url: 'https://finviz.com/', desc: '미국주식 스크리너', cls: 'finviz' },
    { name: 'FRED', short: 'FR', url: 'https://fred.stlouisfed.org/', desc: '금리·유동성·거시', cls: 'fred' },
    { name: 'Investing', short: 'IN', url: 'https://www.investing.com/', desc: '시황·경제 캘린더', cls: 'investing' },
    { name: 'TradingView', short: 'TV', url: 'https://www.tradingview.com/', desc: '차트·기술분석', cls: 'tradingview' },
    { name: 'DART', short: 'D', url: 'https://dart.fss.or.kr/', desc: '한국 기업 공시', cls: 'dart' },
    { name: 'KRX', short: 'KRX', url: 'https://data.krx.co.kr/', desc: '한국거래소 데이터', cls: 'krx' },
    { name: 'Yahoo Finance', short: 'Y!', url: 'https://finance.yahoo.com/', desc: '해외 시세·재무', cls: 'yahoo' },
    { name: '네이버 금융', short: 'N', url: 'https://finance.naver.com/', desc: '국내 시세·뉴스', cls: 'naver' },
  ];

  function iconSvg(tool) {
    const common = 'viewBox="0 0 24 24" aria-hidden="true"';
    if (tool.cls === 'fred') return `<svg ${common}><path d="M3 17l5-5 4 3 7-8"/><path d="M17 7h2v2"/></svg>`;
    if (tool.cls === 'tradingview') return `<svg ${common}><path d="M3 15c3-6 6 4 9-2s6 1 9-5"/><path d="M3 19h18"/></svg>`;
    if (tool.cls === 'investing') return `<svg ${common}><path d="M5 17V9M9 19V5M15 16V8M19 14V6"/><path d="M3 20h18"/></svg>`;
    if (tool.cls === 'dart') return `<svg ${common}><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>`;
    if (tool.cls === 'finviz') return `<svg ${common}><rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><path d="M14 19l2-3 2 1 2-4"/></svg>`;
    return `<span>${tool.short}</span>`;
  }

  function card(tool) {
    return `<a class="investment-tool-card" href="${tool.url}" target="_blank" rel="noopener noreferrer" aria-label="${tool.name} 새 탭에서 열기">
      <span class="investment-tool-icon ${tool.cls}">${iconSvg(tool)}</span>
      <strong>${tool.name}</strong>
      <small>${tool.desc}</small>
    </a>`;
  }

  function install() {
    let tab = document.getElementById('tools-tab');
    if (tab) return tab;
    const macroTab = document.getElementById('macro-tab');
    const chartTab = document.getElementById('chart-tab');
    const anchor = macroTab || chartTab;
    if (!anchor) return null;

    tab = document.createElement('div');
    tab.id = 'tools-tab';
    tab.className = 'tab-content tools-tab-v22';
    tab.innerHTML = `
      <main class="investment-tools-v22">
        <header class="investment-tools-head">
          <span>INVESTMENT TOOLS</span>
          <h2>투자 도구</h2>
          <p>자주 확인하는 투자 사이트를 한곳에 모았습니다. 아이콘을 누르면 새 탭에서 바로 열립니다.</p>
        </header>
        <section class="investment-tools-section">
          <div class="investment-tools-grid">${TOOLS.map(card).join('')}</div>
        </section>
        <div class="investment-tools-note">외부 사이트는 각 서비스에서 직접 제공하며 Chart View는 빠른 이동만 연결합니다.</div>
      </main>`;
    anchor.insertAdjacentElement('beforebegin', tab);
    return tab;
  }

  window.__installInvestmentTools = install;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
