(() => {
  'use strict';

  const TOOLS = [
    { name: 'Finviz', short: 'FZ', domain: 'finviz.com', url: 'https://finviz.com/', desc: '미국주식 스크리너' },
    { name: 'FRED', short: 'FR', domain: 'fred.stlouisfed.org', url: 'https://fred.stlouisfed.org/', desc: '금리·유동성·거시' },
    { name: 'Investing', short: 'IN', domain: 'investing.com', url: 'https://www.investing.com/', desc: '시황·경제 캘린더' },
    { name: 'TradingView', short: 'TV', domain: 'tradingview.com', url: 'https://www.tradingview.com/', desc: '차트·기술분석' },
    { name: 'DART', short: 'D', domain: 'dart.fss.or.kr', url: 'https://dart.fss.or.kr/', desc: '한국 기업 공시' },
    { name: 'KRX', short: 'KRX', domain: 'data.krx.co.kr', url: 'https://data.krx.co.kr/', desc: '한국거래소 데이터' },
    { name: 'Yahoo Finance', short: 'Y!', domain: 'finance.yahoo.com', url: 'https://finance.yahoo.com/', desc: '해외 시세·재무' },
    { name: '네이버 금융', short: 'N', domain: 'finance.naver.com', url: 'https://finance.naver.com/', desc: '국내 시세·뉴스' },
    { name: 'Koyfin', short: 'KY', domain: 'koyfin.com', url: 'https://www.koyfin.com/', desc: '멀티자산 대시보드' },
    { name: 'Macrotrends', short: 'MT', domain: 'macrotrends.net', url: 'https://www.macrotrends.net/', desc: '장기 재무·밸류' },
    { name: 'Trading Economics', short: 'TE', domain: 'tradingeconomics.com', url: 'https://tradingeconomics.com/', desc: '글로벌 거시 데이터' },
    { name: 'Seeking Alpha', short: 'SA', domain: 'seekingalpha.com', url: 'https://seekingalpha.com/', desc: '실적·리서치' },
  ];

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');

  function logo(tool) {
    const src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(tool.domain)}&sz=128`;
    return `<span class="investment-tool-icon">
      <img src="${src}" alt="" width="40" height="40" loading="lazy" referrerpolicy="no-referrer"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
      <span class="investment-tool-fallback" style="display:none">${esc(tool.short)}</span>
    </span>`;
  }

  function card(tool) {
    return `<a class="investment-tool-card" href="${esc(tool.url)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(tool.name)} 새 탭에서 열기">
      ${logo(tool)}
      <strong>${esc(tool.name)}</strong>
      <small>${esc(tool.desc)}</small>
    </a>`;
  }

  function install() {
    let tab = document.getElementById('tools-tab');
    const macroTab = document.getElementById('macro-tab');
    const chartTab = document.getElementById('chart-tab');
    const anchor = macroTab || chartTab;
    if (!anchor && !tab) return null;

    if (!tab) {
      tab = document.createElement('div');
      tab.id = 'tools-tab';
      tab.className = 'tab-content tools-tab-v22';
      anchor.insertAdjacentElement('beforebegin', tab);
    }

    tab.innerHTML = `
      <main class="investment-tools-v22">
        <header class="investment-tools-head">
          <span>INVESTMENT TOOLS</span>
          <h2>투자 도구</h2>
          <p>자주 확인하는 투자 사이트를 한곳에 모았습니다. 로고를 누르면 새 탭에서 바로 열립니다.</p>
        </header>
        <section class="investment-tools-section">
          <div class="investment-tools-grid">${TOOLS.map(card).join('')}</div>
        </section>
        <div class="investment-tools-note">각 로고는 해당 사이트의 공개 favicon을 사용하며, 외부 서비스는 새 탭에서 열립니다.</div>
      </main>`;
    return tab;
  }

  window.__installInvestmentTools = install;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
