from pathlib import Path

path = Path('templates/index.html')
text = path.read_text(encoding='utf-8')
anchor = '    <script src="/static/js/ux_patch.js?v=20260912v32b"></script>\n'
insert = anchor + '    <script src="/static/js/home_watchlist_boot_v32c.js?v=20260912v32c"></script>\n'
if 'home_watchlist_boot_v32c.js' not in text:
    if anchor not in text:
        raise SystemExit('ux_patch v32b anchor not found')
    text = text.replace(anchor, insert, 1)
    path.write_text(text, encoding='utf-8')
print('home watchlist boot loader:', 'ok' if 'home_watchlist_boot_v32c.js' in path.read_text(encoding='utf-8') else 'missing')
