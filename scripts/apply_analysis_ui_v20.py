from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_loader():
    path = ROOT / 'static/js/ux_patch.js'
    text = path.read_text(encoding='utf-8')
    anchor = "  ensureScript('script[data-ux-interactions-v13]', '/static/js/ux_interactions_v13.js?v=20260911v13', 'uxInteractionsV13');\n"
    addition = anchor + "  ensureStyle('link[data-analysis-ui-v20]', '/static/css/analysis_ui_v20.css?v=20260911v20', 'analysisUiV20');\n"
    if "data-analysis-ui-v20" not in text:
        if anchor not in text:
            raise RuntimeError('ux_patch anchor not found')
        text = text.replace(anchor, addition, 1)
    path.write_text(text, encoding='utf-8')


def bust_template():
    path = ROOT / 'templates/index.html'
    text = path.read_text(encoding='utf-8')
    if '/static/js/ux_patch.js?v=20260911v19' in text:
        text = text.replace('/static/js/ux_patch.js?v=20260911v19', '/static/js/ux_patch.js?v=20260911v20')
    elif '/static/js/ux_patch.js?v=20260911v20' not in text:
        raise RuntimeError('template ux_patch version anchor not found')
    path.write_text(text, encoding='utf-8')


def main():
    patch_loader()
    bust_template()
    print('Analysis UI V20 applied')


if __name__ == '__main__':
    main()
