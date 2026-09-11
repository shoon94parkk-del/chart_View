from pathlib import Path
import re


def sub_once(text, pattern, replacement, label, flags=re.S):
    new, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 replacement, got {count}')
    print(f'{label}: applied')
    return new


# -----------------------------------------------------------------------------
# home_brief_v8.js: make the BASE home renderer market-first.
# Do not add a competing renderer/observer (the V14 issue).
# -----------------------------------------------------------------------------
js_path = Path('static/js/home_brief_v8.js')
js = js_path.read_text(encoding='utf-8')

if 'const HOME_MAJOR_STOCKS' not in js:
    anchor = "  function selectedTickersNow() {"
    helpers = r'''  const HOME_MAJOR_STOCKS = [
    { symbol: '005930.KS', name: '삼성전자', domain: 'samsung.com' },
    { symbol: '000660.KS', name: 'SK하이닉스', domain: 'skhynix.com' },
    { symbol: 'NVDA', name: '엔비디아', domain: 'nvidia.com' },
    { symbol: 'AAPL', name: '애플', domain: 'apple.com' },
    { symbol: 'MSFT', name: '마이크로소프트', domain: 'microsoft.com' },
    { symbol: 'META', name: '메타', domain: 'meta.com' },
    { symbol: 'TSLA', name: '테슬라', domain: 'tesla.com' },
    { symbol: 'GOOGL', name: '알파벳', domain: 'google.com' },
  ];

  function homeLogo(item) {
    const initials = esc(String(item.name || item.symbol || '?').replace(/[^0-9A-Za-z가-힣]/g, '').slice(0, 2).toUpperCase() || '?');
    const fallback = `<span class="home16-logo-fallback">${initials}</span>`;
    if (!item.domain) return `<span class="home16-logo">${fallback}</span>`;
    const src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(item.domain)}&sz=128`;
    return `<span class="home16-logo"><img src="${src}" alt="" loading="lazy" decoding="async" onerror="this.style.display='none'">${fallback}</span>`;
  }

  function homePrice(symbol, value) {
    const price = n(value);
    if (price === null) return '-';
    if (/\.(KS|KQ)$/.test(symbol)) return `₩${Math.round(price).toLocaleString('ko-KR')}`;
    return `$${price.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  }

  function homeChangeClass(value) {
    const x = n(value) || 0;
    return x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
  }

  function homeCheckedAt() {
    try {
      return new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
        .format(new Date()).replace(/\. /g, '.').replace(/\.$/, '');
    } catch (_) { return '최신'; }
  }

  function majorRows(heatmap) {
    const map = new Map((heatmap?.results || []).map((row) => [row.ticker, row]));
    return HOME_MAJOR_STOCKS.map((item) => ({ ...item, ...(map.get(item.symbol) || {}) }));
  }

  function majorStocksHtml(rows) {
    return `
      <section class="home-v8-block home16-major-card">
        <div class="home-block-head home16-head">
          <div><span>MARKET</span><h3>주요 종목 오늘 시황</h3></div>
          <small>${esc(homeCheckedAt())} 기준</small>
        </div>
        <div class="home16-stock-strip">${rows.map((row) => `
          <button type="button" class="home16-stock" data-home-symbol="${esc(row.symbol)}" data-home-name="${esc(row.name)}">
            <span class="home16-ring">${homeLogo(row)}</span>
            <strong>${esc(row.name)}</strong>
            <small>${homePrice(row.symbol, row.price)}</small>
            <b class="${homeChangeClass(row.change)}">${pct(row.change, 2)}</b>
          </button>`).join('')}</div>
        <div class="home16-caption">등락률은 직전 종가 대비 · 종목을 누르면 상세 분석으로 이동</div>
      </section>`;
  }

  function moversHtml(rows) {
    const available = rows.filter((row) => n(row.change) !== null);
    const movers = [...available].sort((a, b) => Math.abs(n(b.change)) - Math.abs(n(a.change))).slice(0, 4);
    if (!movers.length) return '';
    return `
      <section class="home-v8-block home16-movers-card">
        <div class="home-block-head home16-head"><div><span>TODAY</span><h3>오늘 많이 움직인 종목</h3></div></div>
        <div class="home16-movers">${movers.map((row, index) => `
          <button type="button" class="home16-mover" data-home-symbol="${esc(row.symbol)}" data-home-name="${esc(row.name)}">
            <span class="home16-mover-rank">${index + 1}</span>
            ${homeLogo(row)}
            <span class="home16-mover-copy"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)} · ${homePrice(row.symbol, row.price)}</small></span>
            <b class="${homeChangeClass(row.change)}">${pct(row.change, 2)}</b><i>›</i>
          </button>`).join('')}</div>
      </section>`;
  }

  function marketSummaryHtml(macro) {
    const summary = typeof macro?.summary === 'string' ? macro.summary : macro?.summary?.text;
    const stale = Number(macro?.staleCount || 0);
    return `
      <section class="home-v8-block home16-summary-card">
        <div class="home-block-head home16-head"><div><span>SUMMARY</span><h3>시장 한줄 요약</h3></div><button type="button" data-home-market>시장 자세히 →</button></div>
        <p>${esc(summary || '주요 지수와 종목별 움직임을 확인해 주세요.')}</p>
        <div class="home16-summary-foot"><span class="${stale ? 'warn' : 'ok'}"></span>${stale ? `일부 매크로 지표 ${stale}개 갱신 지연` : '매크로 데이터 정상 갱신'}</div>
      </section>`;
  }

'''
    if anchor not in js:
        raise SystemExit('home helper anchor not found')
    js = js.replace(anchor, helpers + anchor, 1)

js = sub_once(
    js,
    r"  function installHome\(\) \{.*?\n  \}\n\n  function installBrief\(\)",
    r'''  function installHome() {
    if (document.getElementById('home-tab')) return;
    const chartTab = document.getElementById('chart-tab');
    if (!chartTab) return;
    const tab = document.createElement('div');
    tab.id = 'home-tab';
    tab.className = 'tab-content home-tab';
    tab.innerHTML = `
      <section class="home-v8 home16-market-home">
        <div id="home-v8-body"><div class="home-v8-loading"><div class="spinner"></div><span>오늘 시황을 불러오는 중...</span></div></div>
      </section>`;
    chartTab.insertAdjacentElement('beforebegin', tab);
  }

  function installBrief()''',
    'installHome market-first',
)

js = sub_once(
    js,
    r"  function loadHomeSources\(\) \{.*?\n  \}\n\n  function buildOpportunityRows",
    r'''  function loadHomeSources() {
    if (!homePromise) {
      homePromise = Promise.all([
        fetch('/api/heatmap', { cache: 'no-store' }).then((r) => r.ok ? r.json() : { results: [] }).catch(() => ({ results: [] })),
        fetch('/api/macro', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null).catch(() => null),
      ]);
    }
    return homePromise;
  }

  function buildOpportunityRows''',
    'home source market data',
)

js = sub_once(
    js,
    r"  async function renderHome\(\) \{.*?\n  \}\n\n  function openAnalysis",
    r'''  async function renderHome() {
    const root = document.getElementById('home-v8-body');
    if (!root) return;
    root.innerHTML = '<div class="home-v8-loading"><div class="spinner"></div><span>오늘 시황을 불러오는 중...</span></div>';
    try {
      // Refresh live-ish home data every time Home is opened; stock-detail caches stay untouched.
      homePromise = null;
      const [heatmap, macro] = await loadHomeSources();
      const rows = majorRows(heatmap);
      root.innerHTML = majorStocksHtml(rows) + moversHtml(rows) + marketSummaryHtml(macro);
      bindHomeActions(root);
    } catch (error) {
      console.error('home market dashboard failed', error);
      root.innerHTML = '<div class="home-v8-empty">오늘 시황을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
    }
  }

  function openAnalysis''',
    'renderHome market cards',
)

js_path.write_text(js, encoding='utf-8')
print('home_brief_v8.js updated')


# -----------------------------------------------------------------------------
# home_market_v9: keep the index/macro snapshot, but place it AFTER major stocks.
# -----------------------------------------------------------------------------
market_path = Path('static/js/home_market_v9.js')
market = market_path.read_text(encoding='utf-8')
old = "    home.insertBefore(panel, home.firstChild);"
new = "    home.appendChild(panel);"
if old in market:
    market = market.replace(old, new, 1)
elif new not in market:
    raise SystemExit('home_market_v9 insertion anchor not found')
market_path.write_text(market, encoding='utf-8')
print('home_market_v9 order updated')


# -----------------------------------------------------------------------------
# CSS: append only home-specific V16 rules. Existing stock-detail styles remain.
# -----------------------------------------------------------------------------
css_path = Path('static/css/home_brief_v8.css')
css = css_path.read_text(encoding='utf-8')
marker = '/* HOME V16 MARKET-FIRST */'
if marker not in css:
    css += r'''

/* HOME V16 MARKET-FIRST */
.home16-market-home{max-width:760px;margin:0 auto;padding-top:8px}
.home16-market-home #home-v8-body{display:flex;flex-direction:column;gap:14px}
.home16-market-home .home-v8-block{margin:0;padding:18px;border:1px solid #edf0f2;border-radius:22px;background:#fff;box-shadow:0 8px 28px rgba(15,23,42,.035)}
.home16-head{align-items:center;margin-bottom:14px}
.home16-head>div>span{display:block;margin-bottom:4px;color:#8b95a1;font-size:9px;font-weight:850;letter-spacing:.08em}
.home16-head h3{margin:0;color:#202632;font-size:20px;line-height:1.25;letter-spacing:-.035em}
.home16-head>small{padding:6px 9px;border-radius:999px;background:#f5f7f8;color:#9aa3ad;font-size:9px;font-weight:750;white-space:nowrap}

.home16-stock-strip{display:flex;gap:14px;overflow-x:auto;padding:2px 1px 5px;scrollbar-width:none;scroll-snap-type:x proximity}
.home16-stock-strip::-webkit-scrollbar{display:none}
.home16-stock{flex:0 0 100px;scroll-snap-align:start;padding:0;border:0;background:transparent;text-align:center;font:inherit;cursor:pointer}
.home16-ring{display:flex;align-items:center;justify-content:center;width:76px;height:76px;margin:0 auto 9px;padding:5px;border-radius:50%;background:conic-gradient(#c8ff47 0 34%,#69dfb5 34% 67%,#6bb8f5 67% 100%)}
.home16-ring>.home16-logo{width:66px;height:66px;border:5px solid #fff}
.home16-logo{position:relative;display:inline-flex;align-items:center;justify-content:center;overflow:hidden;border-radius:50%;background:#fff;color:#68727d;font-weight:850}
.home16-logo img{position:relative;z-index:2;width:72%;height:72%;object-fit:contain}
.home16-logo-fallback{position:absolute;z-index:1;font-size:12px;letter-spacing:-.04em}
.home16-stock>strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#3a4652;font-size:12px;font-weight:800}
.home16-stock>small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;color:#9aa3ad;font-size:9px}
.home16-stock>b{display:block;margin-top:3px;font-size:13px;font-variant-numeric:tabular-nums}
.home16-stock b.up,.home16-mover b.up{color:#e04444}.home16-stock b.down,.home16-mover b.down{color:#2673d9}.home16-stock b.flat,.home16-mover b.flat{color:#8b95a1}
.home16-caption{margin-top:10px;color:#a0a8b1;font-size:9px;text-align:right}

.home16-movers{display:flex;flex-direction:column}
.home16-mover{display:grid;grid-template-columns:26px 38px minmax(0,1fr) auto 12px;align-items:center;gap:9px;width:100%;padding:10px 0;border:0;border-bottom:1px solid #f1f3f5;background:transparent;text-align:left;font:inherit;cursor:pointer}
.home16-mover:last-child{border-bottom:0}
.home16-mover-rank{display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:8px;background:#f4f6f8;color:#68727d;font-size:10px;font-weight:850}
.home16-mover>.home16-logo{width:38px;height:38px;border:1px solid #edf0f2}
.home16-mover-copy{min-width:0}
.home16-mover-copy strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#3a4652;font-size:13px;font-weight:800}
.home16-mover-copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:3px;color:#9aa3ad;font-size:9px}
.home16-mover>b{font-size:13px;font-weight:850;font-variant-numeric:tabular-nums;white-space:nowrap}
.home16-mover>i{color:#b0b8c1;font-size:18px;font-style:normal}

.home16-summary-card p{margin:0;padding:14px 15px;border-radius:15px;background:#f7f9fa;color:#46515d;font-size:13px;font-weight:700;line-height:1.55;letter-spacing:-.02em}
.home16-summary-foot{display:flex;align-items:center;gap:7px;margin-top:10px;color:#8b95a1;font-size:9px}
.home16-summary-foot>span{width:7px;height:7px;border-radius:50%}.home16-summary-foot>span.ok{background:#27b060}.home16-summary-foot>span.warn{background:#f0a21b}
.home16-summary-card .home-block-head button{border:0;background:transparent;color:#3182f6;font-size:10px;font-weight:800;cursor:pointer}

@media(max-width:720px){
  .home16-market-home{padding:6px 10px 24px}
  .home16-market-home #home-v8-body{gap:12px}
  .home16-market-home .home-v8-block{padding:16px;border-radius:20px}
  .home16-head{margin-bottom:12px}
  .home16-head h3{font-size:18px}
  .home16-stock-strip{margin-right:-16px;padding-right:16px;gap:11px}
  .home16-stock{flex-basis:88px}
  .home16-ring{width:68px;height:68px}
  .home16-ring>.home16-logo{width:58px;height:58px}
  .home16-stock>strong{font-size:11px}
  .home16-stock>b{font-size:12px}
  .home16-caption{text-align:left}
}
'''
css_path.write_text(css, encoding='utf-8')
print('home_brief_v8.css updated')


# -----------------------------------------------------------------------------
# Cache bust only. V16 still uses the existing base renderer chain.
# -----------------------------------------------------------------------------
uxv3_path = Path('static/js/ux_v3.js')
uxv3 = uxv3_path.read_text(encoding='utf-8')
uxv3 = uxv3.replace('/static/css/home_brief_v8.css?v=20260911v8', '/static/css/home_brief_v8.css?v=20260911v16')
uxv3 = uxv3.replace('/static/js/home_brief_v8.js?v=20260911v8', '/static/js/home_brief_v8.js?v=20260911v16')
uxv3_path.write_text(uxv3, encoding='utf-8')

uxpatch_path = Path('static/js/ux_patch.js')
uxpatch = uxpatch_path.read_text(encoding='utf-8')
uxpatch = uxpatch.replace('/static/js/ux_v3.js?v=20260911v5', '/static/js/ux_v3.js?v=20260911v16')
uxpatch = uxpatch.replace('/static/js/home_market_v9.js?v=20260911v10', '/static/js/home_market_v9.js?v=20260911v16')
uxpatch_path.write_text(uxpatch, encoding='utf-8')

template_path = Path('templates/index.html')
template = template_path.read_text(encoding='utf-8')
template = template.replace('/static/js/ux_patch.js?v=20260911v15', '/static/js/ux_patch.js?v=20260911v16')
template_path.write_text(template, encoding='utf-8')
print('cache versions updated')
