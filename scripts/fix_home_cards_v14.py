from pathlib import Path

js = Path('static/js/home_cards_v14.js')
text = js.read_text(encoding='utf-8')
text = text.replace("      qsa('[data-home14-section]', root).forEach((node) => node.remove());", "      qsa('.home14-stack', root).forEach((node) => node.remove());")
text = text.replace("      if (qs('#home-v8-body')) renderHome14();", "      if (qs('#home-v8-body') && !qs('#home-v8-body .home14-stack')) renderHome14();")
js.write_text(text, encoding='utf-8')

css = Path('static/css/home_cards_v14.css')
text = css.read_text(encoding='utf-8')
text = text.replace('.home14-logo{display:inline-flex;', '.home14-logo{position:relative;display:inline-flex;')
css.write_text(text, encoding='utf-8')

loader = Path('static/js/ux_patch.js')
text = loader.read_text(encoding='utf-8')
text = text.replace('/static/css/home_cards_v14.css?v=20260911v14', '/static/css/home_cards_v14.css?v=20260911v14a')
text = text.replace('/static/js/home_cards_v14.js?v=20260911v14', '/static/js/home_cards_v14.js?v=20260911v14a')
loader.write_text(text, encoding='utf-8')

print('home cards v14 rerender fix ready')
