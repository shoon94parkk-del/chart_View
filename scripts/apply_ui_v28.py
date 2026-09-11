from pathlib import Path


def replace_required(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"required text not found in {path}: {old[:80]}")
    p.write_text(text.replace(old, new), encoding="utf-8")


# 1) Default comparison stocks: AAPL + NVDA + Samsung Electronics.
replace_required(
    "static/js/chart.js",
    "let selectedTickers = ['AAPL', 'NVDA'];",
    "let selectedTickers = ['AAPL', 'NVDA', '005930.KS'];",
)
replace_required(
    "static/js/chart.js",
    "const tickerNameMap = {};",
    "const tickerNameMap = { '005930.KS': '삼성전자' };",
)
replace_required(
    "static/js/fwdper.js",
    "let perTickers = ['AAPL', 'NVDA'];",
    "let perTickers = ['AAPL', 'NVDA', '005930.KS'];",
)
replace_required(
    "static/js/fwdper.js",
    "const perTickerNameMap = {};",
    "const perTickerNameMap = { '005930.KS': '삼성전자' };",
)

# 2) Recommendations collapsed by default + tool asset cache bust.
p = Path("static/js/ux_patch.js")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "/static/css/investment_tools_v22.css?v=20260911v22",
    "/static/css/investment_tools_v22.css?v=20260912v28",
)
s = s.replace(
    "/static/js/investment_tools_v22.js?v=20260911v22",
    "/static/js/investment_tools_v22.js?v=20260912v28",
)
old_toggle = """      toggle.setAttribute('aria-expanded', 'true');
      toggle.innerHTML = '<span>추천 종목</span><span class=\"ux-sector-arrow\">접기 ↑</span>';
      sector.insertBefore(toggle, sector.firstChild);"""
new_toggle = """      sector.classList.add('ux-collapsed');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.innerHTML = '<span>추천 종목</span><span class=\"ux-sector-arrow\">펼치기 ↓</span>';
      sector.insertBefore(toggle, sector.firstChild);"""
if old_toggle not in s:
    raise RuntimeError("recommendation toggle block not found")
s = s.replace(old_toggle, new_toggle)
p.write_text(s, encoding="utf-8")

# 3) Branded tools hub: existing 8 + 4 curated additions.
TOOLS_JS = r'''(() => {
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
'''
Path("static/js/investment_tools_v22.js").write_text(TOOLS_JS, encoding="utf-8")

TOOLS_CSS = r'''/* V28: compact brand-logo investment tools hub. */
.tools-tab-v22{background:#f7f8fa;min-height:calc(100vh - 72px)}
.investment-tools-v22{max-width:760px;margin:0 auto;padding:22px 18px 110px}
.investment-tools-head{padding:4px 4px 18px}
.investment-tools-head>span{display:block;margin-bottom:6px;color:#3182f6;font-size:10px;font-weight:900;letter-spacing:.08em}
.investment-tools-head h2{margin:0;color:#191f28;font-size:27px;font-weight:900;letter-spacing:-.04em}
.investment-tools-head p{margin:7px 0 0;color:#8b95a1;font-size:13px;line-height:1.5}
.investment-tools-section{padding:18px 14px;border:1px solid #e5e8eb;border-radius:22px;background:#fff;box-shadow:0 5px 18px rgba(15,23,42,.035)}
.investment-tools-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px 10px}
.investment-tool-card{min-width:0;color:inherit;text-decoration:none;text-align:center;-webkit-tap-highlight-color:transparent}
.investment-tool-icon{display:flex;align-items:center;justify-content:center;width:58px;height:58px;margin:0 auto 8px;border:1px solid #f0f2f4;border-radius:17px;background:#fff;box-shadow:0 3px 11px rgba(15,23,42,.075);transition:transform .13s ease,box-shadow .13s ease}
.investment-tool-icon img{display:block;width:38px;height:38px;object-fit:contain;border-radius:9px}
.investment-tool-fallback{align-items:center;justify-content:center;width:100%;height:100%;border-radius:17px;background:#f2f4f6;color:#4e5968;font-size:15px;font-weight:900}
.investment-tool-card:active .investment-tool-icon{transform:scale(.94)}
.investment-tool-card:focus-visible{outline:2px solid #3182f6;outline-offset:4px;border-radius:12px}
.investment-tool-card strong{display:block;overflow:hidden;color:#333d4b;font-size:12px;font-weight:820;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.investment-tool-card small{display:block;margin-top:3px;overflow:hidden;color:#a0a8b1;font-size:9px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.investment-tools-note{margin:13px 4px 0;color:#adb5bd;font-size:10px;line-height:1.5}
@media(max-width:720px){
  .investment-tools-v22{padding:16px 14px 100px}
  .investment-tools-head{padding:2px 4px 16px}
  .investment-tools-head h2{font-size:24px}
  .investment-tools-section{padding:18px 10px;border-radius:20px}
  .investment-tools-grid{gap:20px 4px}
  .investment-tool-icon{width:55px;height:55px;border-radius:16px}
  .investment-tool-icon img{width:36px;height:36px}
  .investment-tool-card strong{font-size:11.5px}
  .investment-tool-card small{font-size:8px}
}
@media(max-width:360px){.investment-tool-icon{width:50px;height:50px}.investment-tool-icon img{width:33px;height:33px}.investment-tools-grid{column-gap:2px}}
'''
Path("static/css/investment_tools_v22.css").write_text(TOOLS_CSS, encoding="utf-8")

# 4) Cache-bust direct scripts so mobile browsers cannot keep stale defaults/UX.
p = Path("templates/index.html")
s = p.read_text(encoding="utf-8")
s = s.replace("/static/js/chart.js?v=20260911v27", "/static/js/chart.js?v=20260912v28")
s = s.replace("/static/js/fwdper.js?v=20260911v1", "/static/js/fwdper.js?v=20260912v28")
s = s.replace("/static/js/ux_patch.js?v=20260911v27", "/static/js/ux_patch.js?v=20260912v28")
p.write_text(s, encoding="utf-8")

print("UI V28 patch applied")
