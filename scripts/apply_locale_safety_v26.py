from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_required(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8')
    if old in text:
        text = text.replace(old, new)
    elif new not in text:
        raise RuntimeError(f'{path}: missing target {old}')
    path.write_text(text, encoding='utf-8')


def main():
    replace_required(
        ROOT / 'static/js/home_brief_v8.js',
        "price.toLocaleString(undefined, { maximumFractionDigits: 2 })",
        "price.toLocaleString('en-US', { maximumFractionDigits: 2 })",
    )
    replace_required(
        ROOT / 'static/js/ux_v3.js',
        '/static/js/home_brief_v8.js?v=20260911v22',
        '/static/js/home_brief_v8.js?v=20260911v26',
    )
    replace_required(
        ROOT / 'static/js/ux_patch.js',
        '/static/js/ux_v3.js?v=20260911v25',
        '/static/js/ux_v3.js?v=20260911v26',
    )
    replace_required(
        ROOT / 'templates/index.html',
        '/static/js/ux_patch.js?v=20260911v25',
        '/static/js/ux_patch.js?v=20260911v26',
    )
    print('Locale safety V26 applied')


if __name__ == '__main__':
    main()
