from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def replace_once(path, old, new):
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    if new in text:
        return
    if old not in text:
        raise SystemExit(f'anchor missing: {path}: {old}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

replace_once('templates/index.html', '/static/js/ux_patch.js?v=20260911v23', '/static/js/ux_patch.js?v=20260911v24')
print('V24 browser cache bust applied')
