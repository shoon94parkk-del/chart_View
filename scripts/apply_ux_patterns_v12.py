from pathlib import Path

path = Path('static/js/ux_patch.js')
text = path.read_text(encoding='utf-8')
anchor = "  ensureStyle('link[data-valuation-matrix-v10]', '/static/css/valuation_matrix_v10.css?v=20260911v11', 'valuationMatrixV10');\n"
addition = anchor + "  ensureStyle('link[data-ux-patterns-v12]', '/static/css/ux_patterns_v12.css?v=20260911v12', 'uxPatternsV12');\n  ensureScript('script[data-ux-patterns-v12]', '/static/js/ux_patterns_v12.js?v=20260911v12', 'uxPatternsV12');\n"
if "data-ux-patterns-v12" not in text:
    if anchor not in text:
        raise SystemExit('valuation matrix loader anchor not found')
    text = text.replace(anchor, addition, 1)
    path.write_text(text, encoding='utf-8')
print('ux patterns v12 loader ready')
