from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def required_replace(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8')
    if old in text:
        text = text.replace(old, new)
    elif new not in text:
        raise RuntimeError(f'{path}: missing target: {old}')
    path.write_text(text, encoding='utf-8')


def patch_chart():
    path = ROOT / 'static/js/chart.js'
    text = path.read_text(encoding='utf-8')
    if "localization: { locale: 'ko-KR' }" not in text:
        anchor = "const chartOptions = {\n"
        if anchor not in text:
            raise RuntimeError('chartOptions anchor missing')
        text = text.replace(anchor, anchor + "    localization: { locale: 'ko-KR' },\n", 1)
    path.write_text(text, encoding='utf-8')


def patch_valuation_bands():
    path = ROOT / 'static/js/valuation_bands.js'
    text = path.read_text(encoding='utf-8')
    text = text.replace(
        "Number(v).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})",
        "Number(v).toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d})",
    )
    old = "bandChart=LightweightCharts.createChart(el,{width:el.clientWidth,height:el.clientHeight||340,layout:"
    new = "bandChart=LightweightCharts.createChart(el,{width:el.clientWidth,height:el.clientHeight||340,localization:{locale:'ko-KR'},layout:"
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError('valuation band createChart target missing')
    path.write_text(text, encoding='utf-8')


def patch_all_locale_defaults():
    for path in (ROOT / 'static/js').glob('*.js'):
        text = path.read_text(encoding='utf-8')
        newer = text.replace('.toLocaleString(undefined,', ".toLocaleString('ko-KR',")
        newer = newer.replace('.toLocaleTimeString(undefined,', ".toLocaleTimeString('ko-KR',")
        if newer != text:
            path.write_text(newer, encoding='utf-8')


def patch_html_cache_versions():
    path = ROOT / 'templates/index.html'
    text = path.read_text(encoding='utf-8')
    versions = {
        '/static/js/chart.js?v=20260911v1': '/static/js/chart.js?v=20260911v27',
        '/static/js/valuation_bands.js?v=20260911v1': '/static/js/valuation_bands.js?v=20260911v27',
        '/static/js/ux_patch.js?v=20260911v26': '/static/js/ux_patch.js?v=20260911v27',
    }
    for old, new in versions.items():
        if old in text:
            text = text.replace(old, new)
        elif new not in text:
            raise RuntimeError(f'template target missing: {old}')
    path.write_text(text, encoding='utf-8')


def patch_no_store():
    path = ROOT / 'main.py'
    text = path.read_text(encoding='utf-8')
    old = '''@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
'''
    new = '''@app.get("/")
async def home(request: Request):
    response = templates.TemplateResponse("index.html", {"request": request})
    # Always fetch the current HTML shell; versioned static assets remain cacheable.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
'''
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError('home no-store target missing')
    path.write_text(text, encoding='utf-8')


def main():
    patch_chart()
    patch_valuation_bands()
    patch_all_locale_defaults()
    patch_html_cache_versions()
    patch_no_store()
    print('Samsung locale V27 applied')


if __name__ == '__main__':
    main()
