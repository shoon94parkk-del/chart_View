from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    s = p.read_text(encoding='utf-8')
    if new in s:
        return
    if old not in s:
        raise SystemExit(f'{label}: marker not found in {path}')
    p.write_text(s.replace(old, new, 1), encoding='utf-8')


# 1) App navigation: legacy switchTab calls also participate in browser history,
# while __openAppTab avoids duplicate history entries.
replace_once(
    'static/js/ux_v3.js',
    "  let handlingPopState = false;\n",
    "  let handlingPopState = false;\n  let openingAppTab = 0;\n",
    'navigation guard',
)
replace_once(
    'static/js/ux_v3.js',
    "  function openTab(tabId, options = {}) {\n",
    "  function callLegacySwitch(tabId) {\n    if (typeof window.switchTab !== 'function') return;\n    openingAppTab += 1;\n    try { window.switchTab(tabId); }\n    finally { openingAppTab = Math.max(0, openingAppTab - 1); }\n  }\n\n  function openTab(tabId, options = {}) {\n",
    'legacy switch helper',
)
repls = [
    ("      if (typeof window.switchTab === 'function') window.switchTab('home');", "      callLegacySwitch('home');", 'open home'),
    ("      if (typeof window.switchTab === 'function') window.switchTab('watchlist');", "      callLegacySwitch('watchlist');", 'open watchlist'),
    ("      else if (typeof window.switchTab === 'function') window.switchTab('fwdper');", "      else callLegacySwitch('fwdper');", 'open ideas fallback'),
    ("      else if (typeof window.switchTab === 'function') window.switchTab('screener');", "      else callLegacySwitch('screener');", 'open screener fallback'),
    ("    if (typeof window.switchTab === 'function') window.switchTab(resolved);", "    callLegacySwitch(resolved);", 'open generic'),
]
for old, new, label in repls:
    replace_once('static/js/ux_v3.js', old, new, label)
replace_once(
    'static/js/ux_v3.js',
    "      if (tabId === 'watchlist' && typeof window.__renderWatchlist === 'function') window.__renderWatchlist();\n    };",
    "      if (tabId === 'watchlist' && typeof window.__renderWatchlist === 'function') window.__renderWatchlist();\n      if (!openingAppTab && !handlingPopState && tabId) commitHistory(tabId);\n    };",
    'legacy history bridge',
)
replace_once(
    'static/js/ux_v3.js',
    "        const mode = button.dataset.appMode;\n        if (mode === 'home') openTab('home');",
    "        const mode = button.dataset.appMode;\n        if (button.classList.contains('active')) {\n          window.scrollTo({ top: 0, behavior: 'smooth' });\n          return;\n        }\n        if (mode === 'home') openTab('home');",
    'active tab retap',
)

# 2) Home: all cross-feature moves go through the app navigator.
replace_once(
    'static/js/home_brief_v8.js',
    "    if (typeof window.switchTab === 'function') window.switchTab('chart');",
    "    if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');\n    else if (typeof window.switchTab === 'function') window.switchTab('chart');",
    'home analysis navigation',
)
replace_once(
    'static/js/home_brief_v8.js',
    "      if (typeof window.switchTab === 'function') window.switchTab('revision');",
    "      if (typeof window.__openAppTab === 'function') window.__openAppTab('revision');\n      else if (typeof window.switchTab === 'function') window.switchTab('revision');",
    'home revision navigation',
)
replace_once(
    'static/js/home_brief_v8.js',
    "      const b = document.querySelector('.tab-nav [data-tab=\"screener\"]'); if (b) b.click(); else if (typeof window.switchTab === 'function') window.switchTab('screener');",
    "      if (typeof window.__openAppTab === 'function') window.__openAppTab('screener');\n      else { const b = document.querySelector('.tab-nav [data-tab=\"screener\"]'); if (b) b.click(); else if (typeof window.switchTab === 'function') window.switchTab('screener'); }",
    'home screener navigation',
)
replace_once(
    'static/js/home_brief_v8.js',
    "    root.querySelector('[data-home-market]')?.addEventListener('click', () => { if (typeof window.switchTab === 'function') window.switchTab('macro'); });",
    "    root.querySelector('[data-home-market]')?.addEventListener('click', () => { if (typeof window.__openAppTab === 'function') window.__openAppTab('macro'); else if (typeof window.switchTab === 'function') window.switchTab('macro'); });",
    'home market navigation',
)
replace_once(
    'static/js/home_brief_v8.js',
    "      const appButton = document.querySelector(`[data-app-tab=\"${target}\"]`);\n      if (appButton) appButton.click(); else if (typeof window.switchTab === 'function') window.switchTab(target);",
    "      if (typeof window.__openAppTab === 'function') window.__openAppTab(target);\n      else { const appButton = document.querySelector(`[data-app-tab=\"${target}\"]`); if (appButton) appButton.click(); else if (typeof window.switchTab === 'function') window.switchTab(target); }",
    'brief action navigation',
)

# 3) Screener: analysis actions also use app navigation/history.
replace_once(
    'static/js/screener.js',
    "        if (typeof window.switchTab === 'function') window.switchTab('chart');",
    "        if (typeof window.__openAppTab === 'function') window.__openAppTab('chart');\n        else if (typeof window.switchTab === 'function') window.switchTab('chart');",
    'screener chart navigation',
)
replace_once(
    'static/js/screener.js',
    "        const ideasTab = document.querySelector('[data-tab=\"ideas\"]');\n        if (ideasTab) ideasTab.click();\n        else if (typeof window.switchTab === 'function') window.switchTab('fwdper');",
    "        if (typeof window.__openAppTab === 'function') window.__openAppTab('ideas');\n        else { const ideasTab = document.querySelector('[data-tab=\"ideas\"]'); if (ideasTab) ideasTab.click(); else if (typeof window.switchTab === 'function') window.switchTab('fwdper'); }",
    'screener ideas navigation',
)

# 4) Personalization priority: market strip -> my watchlist -> generic market/stock dashboard.
replace_once(
    'static/js/watchlist_v30.js',
    "      body.insertAdjacentElement('afterend', section);",
    "      body.insertAdjacentElement('beforebegin', section);",
    'home watchlist placement',
)

# 5) Shared compact loading / empty state styling.
states = Path('static/css/app_states_v32.css')
states.write_text(r'''/* App state UX V32: consistent loading/empty surfaces across features. */
.home-v8-loading,
.stock-brief-loading,
.screener-loading,
.macro-loading-inner,
.per-empty,
.home-v8-empty,
.stock-brief-empty,
.screener-empty,
.watchlist-v30-empty {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #edf0f3;
  border-radius: 16px;
  background: #f8fafc;
  color: #6b7684;
}

.home-v8-loading,
.stock-brief-loading,
.screener-loading,
.macro-loading-inner {
  min-height: 104px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 22px 18px;
  font-size: 12px;
  line-height: 1.45;
}

.home-v8-empty,
.stock-brief-empty,
.screener-empty,
.watchlist-v30-empty,
.per-empty {
  min-height: 92px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 5px;
  padding: 18px;
  text-align: left;
  font-size: 12px;
  line-height: 1.5;
}

.watchlist-v30-empty strong { color: #333d4b; font-size: 13px; }
.watchlist-v30-empty p { margin: 0; color: #8b95a1; }

.home-v8-loading .spinner,
.stock-brief-loading .spinner,
.screener-loading .spinner,
.macro-loading-inner .spinner {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
}

@media (max-width: 720px) {
  .home-v8-loading,
  .stock-brief-loading,
  .screener-loading,
  .macro-loading-inner { min-height: 86px; padding: 16px 14px; border-radius: 14px; }
  .home-v8-empty,
  .stock-brief-empty,
  .screener-empty,
  .watchlist-v30-empty,
  .per-empty { min-height: 78px; padding: 14px; border-radius: 14px; }
}
''', encoding='utf-8')

# 6) Cache bust and new stylesheet loader.
p = Path('static/js/ux_patch.js')
s = p.read_text(encoding='utf-8')
s = s.replace('/static/js/screener.js?v=20260912v31', '/static/js/screener.js?v=20260912v32')
s = s.replace('/static/js/watchlist_v30.js?v=20260912v31', '/static/js/watchlist_v30.js?v=20260912v32')
s = s.replace('/static/js/ux_v3.js?v=20260912v30', '/static/js/ux_v3.js?v=20260912v32')
needle = "  ensureStyle('link[data-bottom-nav-v6]', '/static/css/bottom_nav_v6.css?v=20260912v30', 'bottomNavV6');\n"
addition = needle + "  ensureStyle('link[data-app-states-v32]', '/static/css/app_states_v32.css?v=20260912v32', 'appStatesV32');\n"
if "data-app-states-v32" not in s:
    if needle not in s:
        raise SystemExit('ux_patch state style marker missing')
    s = s.replace(needle, addition, 1)
p.write_text(s, encoding='utf-8')

p = Path('static/js/ux_v3.js')
s = p.read_text(encoding='utf-8').replace('/static/js/home_brief_v8.js?v=20260912v29', '/static/js/home_brief_v8.js?v=20260912v32')
p.write_text(s, encoding='utf-8')

p = Path('templates/index.html')
s = p.read_text(encoding='utf-8').replace('/static/js/ux_patch.js?v=20260912v31', '/static/js/ux_patch.js?v=20260912v32')
p.write_text(s, encoding='utf-8')

print('V32 navigation and state UX patch applied')
