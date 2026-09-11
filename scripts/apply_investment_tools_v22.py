from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding='utf-8')
    if new in text:
        print(f'{label}: already applied')
        return
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    print(f'{label}: applied')


TOOLS_JS = r'''(() => {
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
'''

TOOLS_CSS = r'''/* V22: mini-app style external investment tools hub. */
.tools-tab-v22{background:#f7f8fa;min-height:calc(100vh - 72px)}
.investment-tools-v22{max-width:760px;margin:0 auto;padding:22px 18px 110px}
.investment-tools-head{padding:4px 4px 18px}
.investment-tools-head>span{display:block;margin-bottom:6px;color:#3182f6;font-size:10px;font-weight:900;letter-spacing:.08em}
.investment-tools-head h2{margin:0;color:#191f28;font-size:27px;font-weight:900;letter-spacing:-.04em}
.investment-tools-head p{margin:7px 0 0;color:#8b95a1;font-size:13px;line-height:1.5}
.investment-tools-section{padding:18px 14px;border:1px solid #e5e8eb;border-radius:22px;background:#fff;box-shadow:0 5px 18px rgba(15,23,42,.035)}
.investment-tools-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px 10px}
.investment-tool-card{min-width:0;color:inherit;text-decoration:none;text-align:center;-webkit-tap-highlight-color:transparent}
.investment-tool-icon{display:flex;align-items:center;justify-content:center;width:58px;height:58px;margin:0 auto 8px;border-radius:17px;background:#f2f4f6;color:#191f28;font-size:16px;font-weight:950;letter-spacing:-.04em;box-shadow:0 3px 10px rgba(15,23,42,.07);transition:transform .13s ease,box-shadow .13s ease}
.investment-tool-icon svg{width:29px;height:29px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.investment-tool-card:active .investment-tool-icon{transform:scale(.94)}
.investment-tool-card:focus-visible{outline:2px solid #3182f6;outline-offset:4px;border-radius:12px}
.investment-tool-card strong{display:block;overflow:hidden;color:#333d4b;font-size:12px;font-weight:820;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.investment-tool-card small{display:block;margin-top:3px;overflow:hidden;color:#a0a8b1;font-size:9px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.investment-tool-icon.finviz{background:#eef3ff;color:#3156a3}
.investment-tool-icon.fred{background:#eef6ff;color:#1769d2}
.investment-tool-icon.investing{background:#fff3e9;color:#d76a1f}
.investment-tool-icon.tradingview{background:#f0f3ff;color:#2962ff}
.investment-tool-icon.dart{background:#edf9f2;color:#169b62}
.investment-tool-icon.krx{background:#eef7ff;color:#1670bd}
.investment-tool-icon.yahoo{background:#f3edff;color:#6001d2}
.investment-tool-icon.naver{background:#eafbf1;color:#03c75a}
.investment-tools-note{margin:13px 4px 0;color:#adb5bd;font-size:10px;line-height:1.5}
@media(max-width:720px){
  .investment-tools-v22{padding:16px 14px 100px}
  .investment-tools-head{padding:2px 4px 16px}
  .investment-tools-head h2{font-size:24px}
  .investment-tools-section{padding:18px 10px;border-radius:20px}
  .investment-tools-grid{gap:19px 4px}
  .investment-tool-icon{width:55px;height:55px;border-radius:16px}
  .investment-tool-card strong{font-size:11.5px}
  .investment-tool-card small{font-size:8px}
}
@media(max-width:360px){.investment-tool-icon{width:50px;height:50px}.investment-tools-grid{gap-left:2px;gap-right:2px}}
'''


def main():
    (ROOT / 'static/js/investment_tools_v22.js').write_text(TOOLS_JS, encoding='utf-8')
    (ROOT / 'static/css/investment_tools_v22.css').write_text(TOOLS_CSS, encoding='utf-8')

    # Remove duplicated movers block from Home. Keep helper function harmlessly for easy rollback.
    replace_once(
        ROOT / 'static/js/home_brief_v8.js',
        "    root.innerHTML = majorStocksHtml(rows, snapshot?.generatedAt) + moversHtml(rows) + marketSummaryHtml(snapshot?.macro);",
        "    root.innerHTML = majorStocksHtml(rows, snapshot?.generatedAt) + marketSummaryHtml(snapshot?.macro);",
        'remove duplicate movers',
    )

    ux = ROOT / 'static/js/ux_v3.js'
    text = ux.read_text(encoding='utf-8')
    text = text.replace("      script.src = '/static/js/home_brief_v8.js?v=20260911v19';", "      script.src = '/static/js/home_brief_v8.js?v=20260911v22';")
    text = text.replace("    if (tabId === 'home') return 'home';", "    if (tabId === 'home') return 'home';\n    if (tabId === 'tools') return 'tools';")
    text = text.replace("    if (shell) shell.hidden = mode === 'home';", "    if (shell) shell.hidden = mode === 'home' || mode === 'tools';")
    home_block = """    if (tabId === 'home') {
      if (typeof window.switchTab === 'function') window.switchTab('home');
      if (typeof window.__loadHomeDashboard === 'function') window.__loadHomeDashboard();
      return;
    }
"""
    tools_block = home_block + """    if (tabId === 'tools') {
      if (typeof window.__installInvestmentTools === 'function') window.__installInvestmentTools();
      if (typeof window.switchTab === 'function') window.switchTab('tools');
      return;
    }
"""
    if "if (tabId === 'tools')" not in text:
        if home_block not in text: raise SystemExit('openTab home block missing')
        text = text.replace(home_block, tools_block, 1)
    old_bottom = """      <button type=\"button\" class=\"app-bottom-btn\" data-app-mode=\"market\">
        <span class=\"app-bottom-icon\">◎</span><span>시장</span>
      </button>`;
"""
    new_bottom = """      <button type=\"button\" class=\"app-bottom-btn\" data-app-mode=\"tools\">
        <span class=\"app-bottom-icon\">▦</span><span>도구</span>
      </button>`;
"""
    if old_bottom in text:
        text = text.replace(old_bottom, new_bottom, 1)
    elif 'data-app-mode="tools"' not in text:
        raise SystemExit('bottom market button missing')
    text = text.replace("        else if (mode === 'discover') openTab(lastDiscover);\n        else openTab('macro');", "        else if (mode === 'discover') openTab(lastDiscover);\n        else if (mode === 'tools') openTab('tools');\n        else openTab('macro');")
    ux.write_text(text, encoding='utf-8')

    patch = ROOT / 'static/js/ux_patch.js'
    text = patch.read_text(encoding='utf-8')
    text = text.replace("/static/js/ux_v3.js?v=20260911v19", "/static/js/ux_v3.js?v=20260911v22")
    anchor = "  ensureScript('script[data-revision-radar]', '/static/js/revision_radar.js?v=20260911v3', 'revisionRadar');\n"
    addition = anchor + "  ensureStyle('link[data-investment-tools-v22]', '/static/css/investment_tools_v22.css?v=20260911v22', 'investmentToolsV22');\n  ensureScript('script[data-investment-tools-v22]', '/static/js/investment_tools_v22.js?v=20260911v22', 'investmentToolsV22');\n"
    if 'data-investment-tools-v22' not in text:
        if anchor not in text: raise SystemExit('ux_patch asset anchor missing')
        text = text.replace(anchor, addition, 1)
    patch.write_text(text, encoding='utf-8')

    template = ROOT / 'templates/index.html'
    text = template.read_text(encoding='utf-8')
    text = text.replace('/static/js/ux_patch.js?v=20260911v21', '/static/js/ux_patch.js?v=20260911v22')
    template.write_text(text, encoding='utf-8')

    print('Investment tools hub V22 applied')


if __name__ == '__main__':
    main()
