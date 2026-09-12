from pathlib import Path
import re

js = Path('static/js/watchlist_v30.js')
text = js.read_text(encoding='utf-8')
repls = {
    '가격과 1개월 수익률을 홈에서 바로 확인할 수 있습니다.': '가격과 1달 수익률을 홈에서 바로 확인할 수 있습니다.',
    '저장한 종목의 가격과 1개월 흐름을 빠르게 확인합니다.': '저장한 종목의 현재가와 1달 수익률을 빠르게 확인합니다.',
    'aria-label="관심종목 요약"': 'aria-label="관심종목 요약 · 1달 수익률 기준"',
    '<span>상승</span><strong data-watch-summary-up>': '<span>1달 상승</span><strong data-watch-summary-up>',
    '<span>하락</span><strong data-watch-summary-down>': '<span>1달 하락</span><strong data-watch-summary-down>',
    '>수익률↑</button>': '>1달 수익률↑</button>',
    '>수익률↓</button>': '>1달 수익률↓</button>',
    '가격과 1개월 수익률을 한 화면에서 비교할 수 있어요.': '가격과 1달 수익률을 한 화면에서 비교할 수 있어요.',
    '1개월 수익률 · ${quoteFor(row.symbol) ?': '1달 수익률 · ${quoteFor(row.symbol) ?',
    '1개월 수익률 · ${fresh ?': '1달 수익률 · ${fresh ?',
}
for old, new in repls.items():
    if old not in text:
        print('WARN missing:', old)
    text = text.replace(old, new)
js.write_text(text, encoding='utf-8')

ux = Path('static/js/ux_patch.js')
text = ux.read_text(encoding='utf-8')
text = re.sub(r'/static/js/watchlist_v30\.js\?v=[^\'\"]+', '/static/js/watchlist_v30.js?v=20260912v33a', text)
ux.write_text(text, encoding='utf-8')

html = Path('templates/index.html')
text = html.read_text(encoding='utf-8')
text = re.sub(r'/static/js/ux_patch\.js\?v=[^\'\"]+', '/static/js/ux_patch.js?v=20260912v33a', text)
html.write_text(text, encoding='utf-8')

checks = [
    ('header label', '현재가와 1달 수익률' in js.read_text(encoding='utf-8')),
    ('summary up', '1달 상승' in js.read_text(encoding='utf-8')),
    ('summary down', '1달 하락' in js.read_text(encoding='utf-8')),
    ('sort desc', '1달 수익률↑' in js.read_text(encoding='utf-8')),
    ('sort asc', '1달 수익률↓' in js.read_text(encoding='utf-8')),
    ('card meta', '1달 수익률 · ${fresh ?' in js.read_text(encoding='utf-8')),
    ('watch js cache', 'watchlist_v30.js?v=20260912v33a' in ux.read_text(encoding='utf-8')),
    ('ux patch cache', 'ux_patch.js?v=20260912v33a' in html.read_text(encoding='utf-8')),
]
for name, ok in checks:
    print(name, 'OK' if ok else 'MISSING')
    if not ok:
        raise SystemExit(1)
