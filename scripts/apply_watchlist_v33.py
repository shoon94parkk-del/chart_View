from pathlib import Path
import re

js = Path('static/js/watchlist_v30.js')
text = js.read_text(encoding='utf-8')
text = text.replace(
    "(Number(quoteFor(b.symbol)?.return) || -Infinity) - (Number(quoteFor(a.symbol)?.return) || -Infinity)",
    "(Number.isFinite(Number(quoteFor(b.symbol)?.return)) ? Number(quoteFor(b.symbol)?.return) : -Infinity) - (Number.isFinite(Number(quoteFor(a.symbol)?.return)) ? Number(quoteFor(a.symbol)?.return) : -Infinity)"
)
text = text.replace(
    "(Number(quoteFor(a.symbol)?.return) || Infinity) - (Number(quoteFor(b.symbol)?.return) || Infinity)",
    "(Number.isFinite(Number(quoteFor(a.symbol)?.return)) ? Number(quoteFor(a.symbol)?.return) : Infinity) - (Number.isFinite(Number(quoteFor(b.symbol)?.return)) ? Number(quoteFor(b.symbol)?.return) : Infinity)"
)
js.write_text(text, encoding='utf-8')

ux = Path('static/js/ux_patch.js')
text = ux.read_text(encoding='utf-8')
text = re.sub(r'/static/css/watchlist_v30\.css\?v=[^\'\"]+', '/static/css/watchlist_v30.css?v=20260912v33', text)
text = re.sub(r'/static/js/watchlist_v30\.js\?v=[^\'\"]+', '/static/js/watchlist_v30.js?v=20260912v33', text)
ux.write_text(text, encoding='utf-8')

html = Path('templates/index.html')
text = html.read_text(encoding='utf-8')
text = re.sub(r'/static/js/ux_patch\.js\?v=[^\'\"]+', '/static/js/ux_patch.js?v=20260912v33', text)
html.write_text(text, encoding='utf-8')

checks = [
    ('watchlist js cache', 'watchlist_v30.js?v=20260912v33' in ux.read_text(encoding='utf-8')),
    ('watchlist css cache', 'watchlist_v30.css?v=20260912v33' in ux.read_text(encoding='utf-8')),
    ('ux patch cache', 'ux_patch.js?v=20260912v33' in html.read_text(encoding='utf-8')),
    ('v33 quote cache', 'chartview-watchlist-quotes-v33' in js.read_text(encoding='utf-8')),
    ('v33 toolbar', 'data-watch-sort' in js.read_text(encoding='utf-8')),
]
for name, ok in checks:
    print(name, 'OK' if ok else 'MISSING')
    if not ok:
        raise SystemExit(1)
