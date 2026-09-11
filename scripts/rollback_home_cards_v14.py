from pathlib import Path

ux = Path('static/js/ux_patch.js')
text = ux.read_text(encoding='utf-8')
lines = text.splitlines()
lines = [line for line in lines if 'data-home-cards-v14' not in line]
ux.write_text('\n'.join(lines) + '\n', encoding='utf-8')

html = Path('templates/index.html')
text = html.read_text(encoding='utf-8')
text = text.replace('/static/js/ux_patch.js?v=20260911v14', '/static/js/ux_patch.js?v=20260911v15')
html.write_text(text, encoding='utf-8')

print('V14 home cards loader removed; ux_patch cache bumped to v15')
