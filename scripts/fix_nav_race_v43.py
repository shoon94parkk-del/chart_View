from pathlib import Path

path = Path('static/js/ux_v3.js')
text = path.read_text(encoding='utf-8')
old = '''    bottom.querySelectorAll('[data-app-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        userNavigationStarted = true;
        const mode = button.dataset.appMode;
        if (button.classList.contains('active') && !window.ChartViewState?.detail?.open) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        if (mode === 'home') navigateUserTab('home');
'''
new = '''    bottom.querySelectorAll('[data-app-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        userNavigationStarted = true;
        const mode = button.dataset.appMode;
        const visibleTab = [...document.querySelectorAll('.tab-content')].find((tab) => {
          const style = getComputedStyle(tab);
          return !tab.hidden && tab.getAttribute('aria-hidden') !== 'true' && style.display !== 'none' && style.visibility !== 'hidden';
        });
        const visibleTabId = visibleTab?.id?.replace(/-tab$/, '') || '';
        const actualMode = visibleTabId ? modeFor(visibleTabId) : '';
        if (button.classList.contains('active') && actualMode === mode && !window.ChartViewState?.detail?.open) {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          return;
        }
        if (mode === 'home') navigateUserTab('home');
'''
if old not in text:
    raise SystemExit('ux_v3 bottom-nav pattern not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')

path = Path('tests/v41_my_hub.cjs')
text = path.read_text(encoding='utf-8')
old = '''  await page.locator('.app-bottom-btn[data-app-mode="home"]').click();
  await page.waitForSelector('#home-tab', { state: 'visible' });
'''
new = '''  // Reproduce a slow-production race where a stale active class can disagree with the visible tab.
  await page.locator('.app-bottom-btn[data-app-mode="home"]').evaluate(el => el.classList.add('active'));
  await page.locator('.app-bottom-btn[data-app-mode="home"]').click();
  await page.waitForSelector('#home-tab', { state: 'visible' });
'''
if old not in text:
    raise SystemExit('v41_my_hub home-nav pattern not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('V43 navigation race fix applied')
