from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
template = ROOT / 'templates/index.html'
text = template.read_text(encoding='utf-8')
old = '/static/js/ux_patch.js?v=20260911v22'
new = '/static/js/ux_patch.js?v=20260911v23'
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('ux_patch cache-bust anchor not found')
template.write_text(text, encoding='utf-8')
print('HOME UX V23 cache-bust ready')
