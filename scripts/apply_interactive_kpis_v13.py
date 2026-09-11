from pathlib import Path


def replace_once(path, old, new, label):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if new in text:
        print(f'{label}: already applied')
        return
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')
    print(f'{label}: applied')


# 1) Screener: add one extra Plausible-style quick filter layer without replacing
# the existing market/preset/value filters. KPI clicks therefore narrow the current view.
screener = Path('static/js/screener.js')
text = screener.read_text(encoding='utf-8')
marker = "  let sortKey = 'score';\n"
if "let quickFilter = 'none';" not in text:
    if marker not in text:
        raise SystemExit('screener state anchor not found')
    text = text.replace(marker, marker + "  let quickFilter = 'none';\n", 1)

match_anchor = "    if ((row.avgValue20 || 0) < minValue) return false;\n\n    const query ="
match_new = "    if ((row.avgValue20 || 0) < minValue) return false;\n\n    if (quickFilter === 'up' && !((row.change1d || 0) > 0)) return false;\n    if (quickFilter === 'rsi35' && !(row.rsi14 !== null && row.rsi14 !== undefined && Number(row.rsi14) <= 35)) return false;\n    if (quickFilter === 'volume2x' && !((row.volumeRatio || 0) >= 2)) return false;\n\n    const query ="
if "quickFilter === 'up'" not in text:
    if match_anchor not in text:
        raise SystemExit('screener matches anchor not found')
    text = text.replace(match_anchor, match_new, 1)

summary_anchor = "    summary.textContent = `${total.toLocaleString('ko-KR')}개 조건 일치 · ${payload.tradeDate || '-'} 기준 · ${shown.toLocaleString('ko-KR')}개 표시${total > 200 ? ' (상위 200)' : ''}`;"
summary_new = "    const quickLabel = ({ up: '상승 종목만', rsi35: 'RSI 35↓', volume2x: '거래량 2x+' })[quickFilter];\n    summary.textContent = `${total.toLocaleString('ko-KR')}개 조건 일치 · ${payload.tradeDate || '-'} 기준 · ${shown.toLocaleString('ko-KR')}개 표시${total > 200 ? ' (상위 200)' : ''}${quickLabel ? ` · ${quickLabel}` : ''}`;"
if "const quickLabel = ({ up:" not in text:
    if summary_anchor not in text:
        raise SystemExit('screener summary anchor not found')
    text = text.replace(summary_anchor, summary_new, 1)

global_anchor = "  function init() {\n    installTab();\n    bind();\n  }"
global_new = "  window.__setScreenerQuickFilter = function (value = 'none') {\n    const allowed = new Set(['none', 'up', 'rsi35', 'volume2x']);\n    quickFilter = allowed.has(value) ? value : 'none';\n    render();\n    document.dispatchEvent(new CustomEvent('screener:quickfilter', { detail: { value: quickFilter } }));\n    return quickFilter;\n  };\n\n  window.__getScreenerQuickFilter = function () { return quickFilter; };\n\n  function init() {\n    installTab();\n    bind();\n  }"
if "window.__setScreenerQuickFilter" not in text:
    if global_anchor not in text:
        raise SystemExit('screener init anchor not found')
    text = text.replace(global_anchor, global_new, 1)

screener.write_text(text, encoding='utf-8')
print('screener quick-filter API ready')


# 2) Add a small enhancement layer over V12 KPI cards. V12 owns KPI values;
# V13 turns them into tappable controls and keeps the active filter visible.
js = r"""(() => {
  'use strict';

  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
  const FILTERS = [
    { key: 'none', action: '전체 보기' },
    { key: 'up', action: '상승만 보기' },
    { key: 'rsi35', action: '과매도 보기' },
    { key: 'volume2x', action: '급증만 보기' },
  ];

  function numberFrom(text) {
    const match = String(text || '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function currentRsi35Count() {
    return qsa('#screener-results tbody tr')
      .map((row) => numberFrom(qs('td[data-label="RSI"]', row)?.textContent))
      .filter((value) => Number.isFinite(value) && value <= 35).length;
  }

  function updateActive() {
    const current = typeof window.__getScreenerQuickFilter === 'function'
      ? window.__getScreenerQuickFilter() : 'none';
    qsa('#ux12-screener-kpis .ux13-kpi').forEach((button) => {
      const active = button.dataset.ux13Filter === current;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
      const hint = qs('em', button);
      if (hint) {
        if (active && current !== 'none') hint.textContent = '필터 중';
        else if (button.dataset.ux13Filter === 'none' && current !== 'none') hint.textContent = '필터 해제';
        else hint.textContent = FILTERS.find((item) => item.key === button.dataset.ux13Filter)?.action || '보기';
      }
    });
  }

  function enhanceKpis() {
    const strip = qs('#ux12-screener-kpis');
    if (!strip) return false;

    const legacy = Array.from(strip.children).filter((node) => node.tagName === 'DIV');
    if (legacy.length === 4) {
      const rsi35 = currentRsi35Count();
      legacy.forEach((node, index) => {
        const config = FILTERS[index];
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ux13-kpi';
        button.dataset.ux13Filter = config.key;
        button.innerHTML = node.innerHTML;

        if (config.key === 'rsi35') {
          const label = qs('span', button);
          const value = qs('strong', button);
          if (label) label.textContent = 'RSI 35↓';
          if (value) value.textContent = rsi35.toLocaleString('ko-KR');
        }

        const hint = document.createElement('em');
        hint.textContent = config.action;
        button.appendChild(hint);
        button.setAttribute('aria-label', `${qs('span', button)?.textContent || 'KPI'}: ${config.action}`);
        button.addEventListener('click', () => {
          if (typeof window.__setScreenerQuickFilter === 'function') {
            window.__setScreenerQuickFilter(config.key);
          }
          updateActive();
        });
        node.replaceWith(button);
      });
    }

    updateActive();
    if (strip.dataset.ux13Observed !== '1') {
      strip.dataset.ux13Observed = '1';
      new MutationObserver(() => enhanceKpis()).observe(strip, { childList: true });
    }
    return true;
  }

  function boot() {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (enhanceKpis() || attempts >= 80) clearInterval(timer);
    }, 200);

    document.addEventListener('screener:quickfilter', () => setTimeout(enhanceKpis, 0));
    document.addEventListener('click', (event) => {
      if (event.target.closest('[data-tab="screener"], [data-app-mode="discover"]')) {
        setTimeout(enhanceKpis, 250);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
"""
Path('static/js/ux_interactions_v13.js').write_text(js, encoding='utf-8')

css = r"""/* V13: Plausible-style direct interaction on screener KPIs. */
.ux12-screener-kpis>.ux13-kpi{
  position:relative;
  min-width:0;
  padding:9px 10px 8px;
  border:1px solid #edf0f2;
  border-radius:11px;
  background:#fbfcfd;
  color:inherit;
  text-align:left;
  font:inherit;
  cursor:pointer;
  transition:border-color .16s ease,background .16s ease,transform .16s ease,box-shadow .16s ease;
}
.ux12-screener-kpis>.ux13-kpi:hover{border-color:#d5e4fb;background:#f7faff}
.ux12-screener-kpis>.ux13-kpi:active{transform:translateY(1px)}
.ux12-screener-kpis>.ux13-kpi:focus-visible{outline:2px solid #3182f6;outline-offset:2px}
.ux12-screener-kpis>.ux13-kpi.active{border-color:#9fc4ff;background:#f1f6ff;box-shadow:0 0 0 1px rgba(49,130,246,.06)}
.ux12-screener-kpis>.ux13-kpi.active span{color:#1769d2}
.ux12-screener-kpis>.ux13-kpi.active strong{color:#1769d2}
.ux12-screener-kpis>.ux13-kpi em{display:block;margin-top:3px;color:#a0a8b1;font-size:8px;font-style:normal;font-weight:750;line-height:1.1}
.ux12-screener-kpis>.ux13-kpi.active em{color:#3182f6}

@media(max-width:720px){
  .ux12-screener-kpis>.ux13-kpi{padding:7px 5px 6px;border-radius:9px;text-align:center}
  .ux12-screener-kpis>.ux13-kpi em{margin-top:2px;font-size:7px}
}
"""
Path('static/css/ux_interactions_v13.css').write_text(css, encoding='utf-8')
print('v13 interaction assets ready')


# 3) Load V13 after V12 and bust the screener cache so its new quick-filter API is used.
loader = Path('static/js/ux_patch.js')
text = loader.read_text(encoding='utf-8')
text = text.replace("/static/js/screener.js?v=20260911v1", "/static/js/screener.js?v=20260911v13")
anchor = "  ensureScript('script[data-ux-patterns-v12]', '/static/js/ux_patterns_v12.js?v=20260911v12', 'uxPatternsV12');\n"
addition = anchor + "  ensureStyle('link[data-ux-interactions-v13]', '/static/css/ux_interactions_v13.css?v=20260911v13', 'uxInteractionsV13');\n  ensureScript('script[data-ux-interactions-v13]', '/static/js/ux_interactions_v13.js?v=20260911v13', 'uxInteractionsV13');\n"
if "data-ux-interactions-v13" not in text:
    if anchor not in text:
        raise SystemExit('ux_patch V12 loader anchor not found')
    text = text.replace(anchor, addition, 1)
loader.write_text(text, encoding='utf-8')
print('ux_patch v13 loader ready')


# 4) Bust ux_patch itself in the served template.
template = Path('templates/index.html')
text = template.read_text(encoding='utf-8')
text = text.replace('/static/js/ux_patch.js?v=20260911v1', '/static/js/ux_patch.js?v=20260911v13')
template.write_text(text, encoding='utf-8')
print('template cache-bust ready')
