from pathlib import Path
import re

boot = Path('static/js/home_watchlist_boot_v32c.js')
text = boot.read_text(encoding='utf-8')
old = '/static/js/home_polish_v41_4.js?v=20260913v415'
new = '/static/js/home_polish_v41_4.js?v=20260913v415b'
if old not in text:
    raise SystemExit('home polish v415 loader reference missing')
text = text.replace(old, new, 1)
boot.write_text(text, encoding='utf-8')

html = Path('templates/index.html')
text = html.read_text(encoding='utf-8')
text, count = re.subn(r'/static/js/home_watchlist_boot_v32c\.js\?v=[^\"\']+', '/static/js/home_watchlist_boot_v32c.js?v=20260913v415b', text, count=1)
if count != 1:
    raise SystemExit('bootstrap reference not updated')
html.write_text(text, encoding='utf-8')

test = Path('tests/test_v41_5_consistency.py')
text = test.read_text(encoding='utf-8')
text = text.replace('/static/js/home_polish_v41_4.js?v=20260913v415', '/static/js/home_polish_v41_4.js?v=20260913v415b')
text = text.replace('/static/js/home_watchlist_boot_v32c.js?v=20260913v415', '/static/js/home_watchlist_boot_v32c.js?v=20260913v415b')
test.write_text(text, encoding='utf-8')

assert new in boot.read_text(encoding='utf-8')
assert 'home_watchlist_boot_v32c.js?v=20260913v415b' in html.read_text(encoding='utf-8')
print('V41.5b cache bump applied')
