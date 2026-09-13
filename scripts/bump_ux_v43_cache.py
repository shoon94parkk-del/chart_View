from pathlib import Path

p = Path('static/js/ux_patch.js')
text = p.read_text(encoding='utf-8')
old = "'/static/js/ux_v3.js?v=20260912audit1'"
new = "'/static/js/ux_v3.js?v=20260913v43nav1'"
if old not in text:
    raise SystemExit('ux_v3 cache token not found')
p.write_text(text.replace(old, new, 1), encoding='utf-8')
print('bumped ux_v3 cache token')
