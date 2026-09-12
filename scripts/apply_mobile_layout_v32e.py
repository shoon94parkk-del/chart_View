from pathlib import Path

ux = Path('static/js/ux_patch.js')
text = ux.read_text(encoding='utf-8')
text = text.replace('/static/css/bottom_nav_v6.css?v=20260912v30', '/static/css/bottom_nav_v6.css?v=20260912v32e')
text = text.replace('/static/css/home_ux_v23.css?v=20260911v23', '/static/css/home_ux_v23.css?v=20260912v32e')
ux.write_text(text, encoding='utf-8')

html = Path('templates/index.html')
text = html.read_text(encoding='utf-8')
text = text.replace('/static/js/ux_patch.js?v=20260912v32b', '/static/js/ux_patch.js?v=20260912v32e')
html.write_text(text, encoding='utf-8')

checks = [
    ('ux_patch bottom nav', 'bottom_nav_v6.css?v=20260912v32e' in ux.read_text(encoding='utf-8')),
    ('ux_patch home css', 'home_ux_v23.css?v=20260912v32e' in ux.read_text(encoding='utf-8')),
    ('html ux patch', 'ux_patch.js?v=20260912v32e' in html.read_text(encoding='utf-8')),
]
for name, ok in checks:
    print(name, 'OK' if ok else 'MISSING')
    if not ok:
        raise SystemExit(1)
