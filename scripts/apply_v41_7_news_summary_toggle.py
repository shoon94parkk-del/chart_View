from pathlib import Path

js = Path('static/js/news_readability_v41_2.js')
text = js.read_text(encoding='utf-8')
old = '''  function addSummary(card) {\n    if (!card || card.querySelector('.news-v412-summary')) return;\n    const title = card.querySelector('h4');\n    if (!title) return;\n    const box = document.createElement('p');\n    box.className = 'news-v412-summary';\n    box.innerHTML = '<b>한줄 요약 <small>제목 기준</small></b><span></span>';\n    box.querySelector('span').textContent = oneLineSummary(title.textContent);\n    title.insertAdjacentElement('afterend', box);\n  }\n'''
new = '''  function addSummary(card) {\n    if (!card || card.querySelector('.news-v412-summary')) return;\n    const title = card.querySelector('h4');\n    if (!title) return;\n    const box = document.createElement('button');\n    box.type = 'button';\n    box.className = 'news-v412-summary';\n    box.setAttribute('aria-expanded', 'false');\n    box.setAttribute('aria-label', '한줄 요약 전체보기');\n    box.innerHTML = '<span class="news-v417-summary-head"><b>한줄 요약 <small>제목 기준</small></b><i>전체보기</i></span><span class="news-v417-summary-text"></span>';\n    box.querySelector('.news-v417-summary-text').textContent = oneLineSummary(title.textContent);\n    box.addEventListener('click', () => {\n      const expanded = box.getAttribute('aria-expanded') === 'true';\n      box.setAttribute('aria-expanded', String(!expanded));\n      box.classList.toggle('is-expanded', !expanded);\n      box.querySelector('.news-v417-summary-head i').textContent = expanded ? '전체보기' : '접기';\n      box.setAttribute('aria-label', expanded ? '한줄 요약 전체보기' : '한줄 요약 접기');\n    });\n    title.insertAdjacentElement('afterend', box);\n  }\n'''
if old not in text:
    raise SystemExit('addSummary block not found')
text = text.replace(old, new, 1)
text = text.replace("home.dataset.newsReadability = 'v41.2'", "home.dataset.newsReadability = 'v41.7'")
text = text.replace("hub.dataset.newsReadability = 'v41.2'", "hub.dataset.newsReadability = 'v41.7'")
js.write_text(text, encoding='utf-8')

css = Path('static/css/news_readability_v41_2.css')
css_text = css.read_text(encoding='utf-8')
append = '''\n/* V41.7: readable, tappable news summary */\n.news-v412-summary{width:100%;box-sizing:border-box;border:0;text-align:left;font:inherit;cursor:pointer;appearance:none;-webkit-appearance:none}\n.news-v417-summary-head{display:flex;align-items:center;justify-content:space-between;gap:10px}\n.news-v417-summary-head>b{display:flex;align-items:center;gap:7px;color:var(--text-primary,#111827);font-size:11.5px}\n.news-v417-summary-head b small{font-size:9px;font-weight:700;padding:2px 6px;border-radius:999px;background:rgba(37,99,235,.09);color:var(--accent,#2563eb)}\n.news-v417-summary-head i{font-style:normal;font-size:10px;font-weight:800;color:var(--accent,#2563eb);white-space:nowrap}\n.news-v417-summary-text{display:-webkit-box!important;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;line-height:1.55;margin-top:5px}\n.news-v412-summary.is-expanded .news-v417-summary-text{-webkit-line-clamp:unset;display:block!important;overflow:visible}\n.news-v412-summary:focus-visible{outline:2px solid var(--accent,#2563eb);outline-offset:2px}\n.news-v40-card.is-lead .news-v417-summary-head>b{color:#fff}\n.news-v40-card.is-lead .news-v417-summary-head b small{background:rgba(255,255,255,.12);color:#dbeafe}\n.news-v40-card.is-lead .news-v417-summary-head i{color:#bfdbfe}\n.news-v40-card.is-lead .news-v417-summary-text{color:rgba(255,255,255,.82)}\n@media(max-width:720px){.news-v417-summary-head i{font-size:9.5px}.news-v417-summary-text{font-size:11.5px}}\n'''
if 'V41.7: readable, tappable news summary' not in css_text:
    css_text += append
css.write_text(css_text, encoding='utf-8')

boot = Path('static/js/home_watchlist_boot_v32c.js')
boot_text = boot.read_text(encoding='utf-8')
boot_text = boot_text.replace('/static/css/news_readability_v41_2.css?v=20260913v412', '/static/css/news_readability_v41_2.css?v=20260913v417')
boot_text = boot_text.replace('/static/js/news_readability_v41_2.js?v=20260913v415', '/static/js/news_readability_v41_2.js?v=20260913v417')
boot.write_text(boot_text, encoding='utf-8')

html = Path('templates/index.html')
html_text = html.read_text(encoding='utf-8')
html_text = html_text.replace('/static/js/home_watchlist_boot_v32c.js?v=20260913v415b', '/static/js/home_watchlist_boot_v32c.js?v=20260913v417')
html.write_text(html_text, encoding='utf-8')

# Permanent regression coverage.
test = Path('tests/test_v41_7_news_summary_toggle.py')
test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_news_summary_is_expandable_and_cache_busted():\n    js = (ROOT / "static/js/news_readability_v41_2.js").read_text(encoding="utf-8")\n    css = (ROOT / "static/css/news_readability_v41_2.css").read_text(encoding="utf-8")\n    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")\n    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")\n    assert "document.createElement('button')" in js\n    assert "aria-expanded" in js\n    assert "한줄 요약 전체보기" in js\n    assert "news-v417-summary-text" in js\n    assert ".news-v412-summary.is-expanded .news-v417-summary-text" in css\n    assert "-webkit-line-clamp:2" in css\n    assert "news_readability_v41_2.css?v=20260913v417" in boot\n    assert "news_readability_v41_2.js?v=20260913v417" in boot\n    assert "home_watchlist_boot_v32c.js?v=20260913v417" in html\n''', encoding='utf-8')

print('V41.7 summary toggle applied')
