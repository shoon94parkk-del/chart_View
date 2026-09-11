from pathlib import Path

loader = Path('static/js/ux_patch.js')
text = loader.read_text(encoding='utf-8')
anchor = "  ensureScript('script[data-ux-interactions-v13]', '/static/js/ux_interactions_v13.js?v=20260911v13', 'uxInteractionsV13');\n"
addition = anchor + "  ensureStyle('link[data-home-cards-v14]', '/static/css/home_cards_v14.css?v=20260911v14', 'homeCardsV14');\n  ensureScript('script[data-home-cards-v14]', '/static/js/home_cards_v14.js?v=20260911v14', 'homeCardsV14');\n"
if 'data-home-cards-v14' not in text:
    if anchor not in text:
        raise SystemExit('V13 loader anchor not found')
    text = text.replace(anchor, addition, 1)
loader.write_text(text, encoding='utf-8')
print('home cards v14 loader ready')

template = Path('templates/index.html')
text = template.read_text(encoding='utf-8')
text = text.replace('/static/js/ux_patch.js?v=20260911v13', '/static/js/ux_patch.js?v=20260911v14')
template.write_text(text, encoding='utf-8')
print('template cache bust v14 ready')
