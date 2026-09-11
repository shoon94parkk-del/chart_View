from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, pattern: str, repl: str, flags=re.S):
    text = path.read_text(encoding='utf-8')
    new, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f'{path}: pattern not found')
    path.write_text(new, encoding='utf-8')


def patch_ux_v3():
    path = ROOT / 'static/js/ux_v3.js'
    replacement = r'''  function observeLateUI() {
    // Mobile stability: no document.body-wide observer and no rapid polling loop.
    const settle = () => {
      wrapSwitchTab();
      installAppNavigation();
      revealAllValuationMetrics();
      revealAllDateControls();
      restoreScreenerControls();
    };
    queueMicrotask(settle);
    setTimeout(settle, 350);
    setTimeout(settle, 1200);
  }

  function init()'''
    replace_once(path, r"  function observeLateUI\(\) \{.*?\n  \}\n\n  function init\(\)", replacement)


def patch_ux_patch():
    path = ROOT / 'static/js/ux_patch.js'
    text = path.read_text(encoding='utf-8')
    old = '''  function watchValuationTable() {
    const container = document.getElementById('per-table-container');
    if (!container) return;
    enhanceValuationTable();
    const observer = new MutationObserver(() => enhanceValuationTable());
    observer.observe(container, { childList: true, subtree: true });
  }'''
    new = '''  function watchValuationTable() {
    const container = document.getElementById('per-table-container');
    if (!container) return;
    // Mobile stability: valuation labels are best-effort, never continuously observed.
    enhanceValuationTable();
    setTimeout(enhanceValuationTable, 900);
  }'''
    if old not in text:
        raise RuntimeError('watchValuationTable target missing')
    text = text.replace(old, new, 1)
    text = text.replace('    loadUniverse();\n    watchValuationTable();', '    // KRX universe is lazy-loaded only when the user searches.\n    watchValuationTable();', 1)
    text = text.replace("/static/js/ux_v3.js?v=20260911v22", "/static/js/ux_v3.js?v=20260911v25")
    text = text.replace("/static/js/home_market_v9.js?v=20260911v24", "/static/js/home_market_v9.js?v=20260911v25")
    text = text.replace("/static/js/home_ux_v23.js?v=20260911v24", "/static/js/home_ux_v23.js?v=20260911v25")
    path.write_text(text, encoding='utf-8')


def patch_home_ux():
    path = ROOT / 'static/js/home_ux_v23.js'
    replacement = r'''  function boot() {
    // Mobile stability: a few scheduled idempotent passes, never a rapid interval.
    requestAnimationFrame(stabilizeHome);
    setTimeout(stabilizeHome, 400);
    setTimeout(stabilizeHome, 1200);

    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn[data-app-mode="home"]')) {
        setTimeout(stabilizeHome, 100);
      }
    });
  }

  if (document.readyState'''
    replace_once(path, r"  function boot\(\) \{.*?\n  \}\n\n  if \(document\.readyState", replacement)


def patch_home_market():
    path = ROOT / 'static/js/home_market_v9.js'
    text = path.read_text(encoding='utf-8')
    observer_old = '''  function installHomeChromeObserver() {
    syncHomeChrome();
    const watched = new WeakSet();
    const watchTargets = () => {
      [
        document.getElementById('home-tab'),
        document.querySelector('.app-bottom-btn[data-app-mode="home"]'),
      ].filter(Boolean).forEach((node) => {
        if (watched.has(node)) return;
        watched.add(node);
        new MutationObserver(syncHomeChrome).observe(node, { attributes: true, attributeFilter: ['class'] });
      });
      syncHomeChrome();
    };
    watchTargets();
    setTimeout(watchTargets, 250);
    setTimeout(watchTargets, 1000);
  }'''
    observer_new = '''  function installHomeChromeObserver() {
    // Mobile stability: navigation click handlers already keep this state in sync.
    syncHomeChrome();
    setTimeout(syncHomeChrome, 300);
    setTimeout(syncHomeChrome, 1200);
  }'''
    if observer_old not in text:
        raise RuntimeError('home chrome observer target missing')
    text = text.replace(observer_old, observer_new, 1)

    init_pattern = r'''  function init\(\) \{.*?\n  \}\n\n  if \(document\.readyState'''
    init_repl = r'''  function init() {
    installHomeChromeObserver();

    const tryInit = (attempt = 0) => {
      syncHomeChrome();
      const panel = ensurePanel();
      if (panel) {
        const local = readMarketLocal();
        if (local) paintMarket(panel, local);
        loadMarket(false);
        setTimeout(() => loadMarket(true), 600);
        startRefreshLoop();
        return;
      }
      if (attempt < 10) setTimeout(() => tryInit(attempt + 1), 300);
    };
    tryInit();

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && isHomeActive()) loadMarket(true);
    });
    document.addEventListener('click', (event) => {
      if (event.target.closest('.app-bottom-btn')) {
        requestAnimationFrame(() => {
          syncHomeChrome();
          if (isHomeActive()) {
            ensurePanel();
            loadMarket();
          }
        });
      }
    });
  }

  if (document.readyState'''
    new, count = re.subn(init_pattern, init_repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError('home market init target missing')
    path.write_text(new, encoding='utf-8')


def bump_template():
    path = ROOT / 'templates/index.html'
    text = path.read_text(encoding='utf-8')
    if '/static/js/ux_patch.js?v=20260911v24' in text:
        text = text.replace('/static/js/ux_patch.js?v=20260911v24', '/static/js/ux_patch.js?v=20260911v25')
    elif '/static/js/ux_patch.js?v=20260911v25' not in text:
        raise RuntimeError('template ux_patch cache target missing')
    path.write_text(text, encoding='utf-8')


def main():
    patch_ux_v3()
    patch_ux_patch()
    patch_home_ux()
    patch_home_market()
    bump_template()
    print('Mobile stability V25 applied')


if __name__ == '__main__':
    main()
