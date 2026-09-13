from pathlib import Path


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace(path, old, new, count=1):
    text = read(path)
    if old not in text:
        raise SystemExit(f'missing pattern: {path}: {old[:120]}')
    text = text.replace(old, new, count)
    write(path, text)


replace(
    'main.py',
    'from news_service_v37 import router as news_router_v37\n',
    'from news_service_v37 import router as news_router_v37\nfrom news_summary_service import router as news_summary_router_v43\n',
)
replace(
    'main.py',
    'app.include_router(news_router_v37)\n',
    'app.include_router(news_router_v37)\napp.include_router(news_summary_router_v43)\n',
)

# Preserve a short provider-supplied article summary/excerpt only as a fallback seed.
path = 'news_service_v37.py'
text = read(path)
needle = '            "relationBasis": relation_basis,\n        })'
if text.count(needle) != 2:
    raise SystemExit(f'expected 2 news item insertions, got {text.count(needle)}')
text = text.replace(
    needle,
    '            "relationBasis": relation_basis,\n            "summarySeed": context[:700],\n        })',
)
text = text.replace(
    '- Return headline/source/time/original URL only; never proxy article body or images.',
    '- Return headline/source/time/original URL plus a short provider summary seed; never proxy article body or images.',
)
text = text.replace('"displayPolicy": "headline-source-time-link-only"', '"displayPolicy": "headline-source-time-link-summary-seed"')
text = text.replace(
    '"notice": "기사 본문과 이미지는 저장·재게시하지 않고 원문 링크로 연결합니다.",',
    '"notice": "기사 본문·이미지는 저장하거나 재게시하지 않으며, 화면 요약은 원문을 일시적으로 읽어 한국어 요약만 생성합니다.",',
)
write(path, text)

replace(
    'static/js/personalized_news_v40.js',
    'return `<article class="news-v40-card ${index === 0 ? \'is-lead\' : \'\'}" data-impact="${meta.level}" data-news-symbol="${esc(item.symbol)}">',
    'return `<article class="news-v40-card ${index === 0 ? \'is-lead\' : \'\'}" data-impact="${meta.level}" data-news-symbol="${esc(item.symbol)}" data-news-summary-seed="${esc(item.summarySeed || \'\')}">',
)
replace(
    'static/js/my_hub_v41.js',
    'return `<article class="my-hub-v41-news-row" data-related-symbols="${esc((item.relatedSymbols || []).join(\',\'))}">',
    'return `<article class="my-hub-v41-news-row" data-related-symbols="${esc((item.relatedSymbols || []).join(\',\'))}" data-news-summary-seed="${esc(item.summarySeed || \'\')}">',
)

replace(
    'static/js/home_watchlist_boot_v32c.js',
    "'/static/css/news_readability_v41_2.css?v=20260913v42'",
    "'/static/css/news_readability_v41_2.css?v=20260913v43'",
)
replace(
    'static/js/home_watchlist_boot_v32c.js',
    "'/static/js/news_readability_v41_2.js?v=20260913v42'",
    "'/static/js/news_readability_v41_2.js?v=20260913v43'",
)
replace(
    'static/js/home_watchlist_boot_v32c.js',
    "home.dataset.newsReadability = 'v41.2'",
    "home.dataset.newsReadability = 'v43'",
)
replace(
    'templates/index.html',
    'home_watchlist_boot_v32c.js?v=20260913v42',
    'home_watchlist_boot_v32c.js?v=20260913v43',
)

# Old test asserted that the list API could never expose a provider summary seed.
replace(
    'tests/test_v37_personalized_news.py',
    'assert payload["displayPolicy"] == "headline-source-time-link-only"',
    'assert payload["displayPolicy"] == "headline-source-time-link-summary-seed"',
)

css_path = Path('static/css/news_readability_v41_2.css')
css = css_path.read_text(encoding='utf-8')
marker = '/* V43: body-based Korean news summaries */'
if marker not in css:
    css += '''\n\n/* V43: body-based Korean news summaries */\n.news-v412-summary.is-loading .news-v417-summary-text{opacity:.62}\n.news-v412-summary.is-loading .news-v417-summary-head small{animation:v43-summary-pulse 1.2s ease-in-out infinite}\n.news-v412-summary.is-error .news-v417-summary-head small{background:rgba(239,68,68,.09);color:#dc2626}\n@keyframes v43-summary-pulse{0%,100%{opacity:.55}50%{opacity:1}}\n@media(prefers-reduced-motion:reduce){.news-v412-summary.is-loading .news-v417-summary-head small{animation:none}}\n'''
    css_path.write_text(css, encoding='utf-8')

print('V43 news summary wiring applied')
