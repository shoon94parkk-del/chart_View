from pathlib import Path


def patch_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    s = p.read_text(encoding='utf-8')
    if new in s:
        return
    if old not in s:
        raise SystemExit(f'{label}: marker not found in {path}')
    p.write_text(s.replace(old, new, 1), encoding='utf-8')


# Screener: one-tap watchlist star.
patch_once(
    'static/js/screener.js',
    '''<td data-label="액션"><div class="screen-actions"><button class="screen-add" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">비교+</button><button class="screen-idea" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">아이디어</button></div></td>''',
    '''<td data-label="액션"><div class="screen-actions"><button class="screen-add" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">비교+</button><button class="screen-idea" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}">아이디어</button><button class="screen-watch ${typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(row.symbol) ? 'active' : ''}" data-symbol="${esc(row.symbol)}" data-name="${esc(row.name)}" aria-label="${esc(row.name)} 관심종목">${typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(row.symbol) ? '★' : '☆'}</button></div></td>''',
    'screener action',
)
patch_once(
    'static/js/screener.js',
    '''    results.querySelectorAll('.screen-idea').forEach((button) => {''',
    '''    results.querySelectorAll('.screen-watch').forEach((button) => {
      button.addEventListener('click', () => {
        if (typeof window.__toggleWatchlist !== 'function') return;
        window.__toggleWatchlist(button.dataset.symbol, button.dataset.name);
        const active = typeof window.__isWatchlisted === 'function' && window.__isWatchlisted(button.dataset.symbol);
        button.classList.toggle('active', active);
        button.textContent = active ? '★' : '☆';
      });
    });

    results.querySelectorAll('.screen-idea').forEach((button) => {''',
    'screener watch listener',
)

# Watchlist: keep a compact Home shortcut synchronized.
patch_once(
    'static/js/watchlist_v30.js',
    '''    saveWatchlist();
    render();
    enhanceTickerStars();''',
    '''    saveWatchlist();
    document.dispatchEvent(new CustomEvent('chartview:watchlist-change'));
    render();
    renderHomeShortcut();
    enhanceTickerStars();''',
    'watchlist toggle',
)

home_fn = r'''  function renderHomeShortcut() {
    const body = document.getElementById('home-v8-body');
    if (!body) return false;
    let section = document.getElementById('home-watchlist-v30');
    if (!section) {
      section = document.createElement('section');
      section.id = 'home-watchlist-v30';
      section.className = 'home-v8-block home-watchlist-v30';
      body.insertAdjacentElement('afterend', section);
    }
    const visible = watchlist.slice(0, 4);
    section.innerHTML = `
      <div class="home-block-head home-watchlist-v30-head">
        <div><span>MY STOCKS</span><h3>내 관심종목</h3></div>
        <button type="button" data-home-watch-all>전체보기 →</button>
      </div>
      ${visible.length ? `<div class="home-watchlist-v30-chips">${visible.map((row) => `<button type="button" data-home-watch-open="${esc(row.symbol)}" data-home-watch-name="${esc(row.name)}"><strong>${esc(row.name)}</strong><small>${esc(row.symbol)}</small></button>`).join('')}</div>` : '<p class="home-watchlist-v30-empty">관심종목을 추가하면 홈에서 바로 이동할 수 있습니다.</p>'}`;
    section.querySelector('[data-home-watch-all]')?.addEventListener('click', () => {
      if (typeof window.__openAppTab === 'function') window.__openAppTab('watchlist');
    });
    section.querySelectorAll('[data-home-watch-open]').forEach((button) => button.addEventListener('click', () => openAnalysis(button.dataset.homeWatchOpen, button.dataset.homeWatchName)));
    return true;
  }

'''
patch_once('static/js/watchlist_v30.js', '  function installTab() {', home_fn + '  function installTab() {', 'home watch shortcut')
patch_once(
    'static/js/watchlist_v30.js',
    '''    render();
    document.addEventListener('click', (event) => {''',
    '''    render();
    setTimeout(renderHomeShortcut, 500);
    setTimeout(renderHomeShortcut, 1800);
    document.addEventListener('chartview:watchlist-change', renderHomeShortcut);
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) setTimeout(renderHomeShortcut, 250);''',
    'watchlist init shortcut',
)
patch_once(
    'static/js/watchlist_v30.js',
    '  window.__recordRecentTicker = recordRecent;',
    '''  window.__recordRecentTicker = recordRecent;
  window.__renderHomeWatchlist = renderHomeShortcut;''',
    'watchlist export',
)

# CSS additions.
p = Path('static/css/screener.css')
s = p.read_text(encoding='utf-8')
if '/* watchlist-action-v31 */' not in s:
    s += r'''

/* watchlist-action-v31 */
.screen-watch{border:1px solid #e5e8eb;border-radius:9px;min-width:34px;padding:7px 9px;background:#fff;color:#b0b8c1;font-size:15px;font-weight:800;cursor:pointer}
.screen-watch.active{border-color:#f7cf78;background:#fff8e1;color:#f5a623}
@media(max-width:720px){
  .screen-actions{grid-template-columns:minmax(0,1fr) minmax(0,1fr) 38px!important}
  .screen-watch{width:38px;min-width:38px;min-height:34px;padding:4px;font-size:16px}
}
'''
    p.write_text(s, encoding='utf-8')

p = Path('static/css/watchlist_v30.css')
s = p.read_text(encoding='utf-8')
if '/* home-watchlist-v31 */' not in s:
    s += r'''

/* home-watchlist-v31 */
.home-watchlist-v30{margin-top:12px;padding:18px;border:1px solid #e5e8eb;border-radius:20px;background:#fff;box-shadow:0 8px 26px rgba(15,23,42,.04)}
.home-watchlist-v30-head{margin-bottom:12px}
.home-watchlist-v30-head button{border:0;background:transparent;color:#3182f6;font-size:12px;font-weight:800;cursor:pointer}
.home-watchlist-v30-chips{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.home-watchlist-v30-chips button{min-width:0;padding:12px 10px;border:1px solid #edf0f3;border-radius:14px;background:#f7f9fb;text-align:left;cursor:pointer}
.home-watchlist-v30-chips strong,.home-watchlist-v30-chips small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.home-watchlist-v30-chips strong{font-size:13px;color:#191f28}.home-watchlist-v30-chips small{margin-top:4px;font-size:9.5px;color:#8b95a1}
.home-watchlist-v30-empty{margin:0;color:#8b95a1;font-size:12px}
@media(max-width:720px){
  .home-watchlist-v30{margin:10px 0 0;padding:15px;border-radius:18px}
  .home-watchlist-v30-chips{grid-template-columns:repeat(2,minmax(0,1fr))}
}
'''
    p.write_text(s, encoding='utf-8')

# Cache bust.
p = Path('static/js/ux_patch.js')
s = p.read_text(encoding='utf-8')
s = s.replace('/static/js/screener.js?v=20260912v29', '/static/js/screener.js?v=20260912v31')
s = s.replace('/static/css/screener.css?v=20260911v3', '/static/css/screener.css?v=20260912v31')
s = s.replace('/static/js/watchlist_v30.js?v=20260912v30', '/static/js/watchlist_v30.js?v=20260912v31')
s = s.replace('/static/css/watchlist_v30.css?v=20260912v30', '/static/css/watchlist_v30.css?v=20260912v31')
p.write_text(s, encoding='utf-8')

p = Path('templates/index.html')
s = p.read_text(encoding='utf-8').replace('/static/js/ux_patch.js?v=20260912v30', '/static/js/ux_patch.js?v=20260912v31')
p.write_text(s, encoding='utf-8')

print('V31 watchlist UX patch applied')
