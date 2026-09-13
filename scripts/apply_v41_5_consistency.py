from pathlib import Path
import re


def replace(path, old, new, count=-1):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing pattern in {path}: {old[:120]}')
    text = text.replace(old, new, count)
    p.write_text(text, encoding='utf-8')

# 1) Five-day compare must represent five trading-day closes, not a tail of intraday bars.
replace('market_service.py', '"1d": "5m", "5d": "15m", "1mo": "1d",', '"1d": "5m", "5d": "1d", "1mo": "1d",')

# 2) Balance personalized-news highlights across symbols before filling with extra stories.
news = Path('news_service_v37.py')
text = news.read_text(encoding='utf-8')
needle = '''def _dedupe(items: list[dict]) -> list[dict]:\n    seen_urls: set[str] = set()\n    seen_titles: set[str] = set()\n    out: list[dict] = []\n    for row in sorted(items, key=lambda x: (-float(x.get("score") or 0), -float(x.get("publishedTs") or 0))):\n        url = str(row.get("url") or "").strip()\n        title_key = re.sub(r"[^0-9a-z가-힣]+", "", str(row.get("title") or "").lower())[:120]\n        if not url or not title_key or url in seen_urls or title_key in seen_titles:\n            continue\n        seen_urls.add(url)\n        seen_titles.add(title_key)\n        out.append(row)\n    return out\n'''
if needle not in text:
    raise SystemExit('dedupe function pattern missing')
addition = needle + '''\n\ndef _balanced_highlights(items: list[dict], limit: int = 12) -> list[dict]:\n    """Keep relevance while preventing one active ticker from monopolizing Home highlights."""\n    ranked = _dedupe(items)\n    if not ranked or limit <= 0:\n        return []\n\n    first_by_symbol: dict[str, dict] = {}\n    for row in ranked:\n        symbol = str(row.get("symbol") or "").upper()\n        if symbol and symbol not in first_by_symbol:\n            first_by_symbol[symbol] = row\n\n    primary = sorted(\n        first_by_symbol.values(),\n        key=lambda x: (-float(x.get("score") or 0), -float(x.get("publishedTs") or 0)),\n    )\n    chosen = primary[:limit]\n    chosen_ids = {(str(row.get("url") or ""), str(row.get("title") or "")) for row in chosen}\n    if len(chosen) < limit:\n        for row in ranked:\n            identity = (str(row.get("url") or ""), str(row.get("title") or ""))\n            if identity in chosen_ids:\n                continue\n            chosen.append(row)\n            chosen_ids.add(identity)\n            if len(chosen) >= limit:\n                break\n    return chosen\n'''
text = text.replace(needle, addition, 1)
text = text.replace('highlights = _dedupe(all_items)[:12]', 'highlights = _balanced_highlights(all_items, 12)', 1)
news.write_text(text, encoding='utf-8')

# 3) Frontend defense: Home TOP3 prefers distinct tickers even if an older backend response is cached.
p = Path('static/js/personalized_news_v40.js')
text = p.read_text(encoding='utf-8')
text = text.replace(
"""  function renderArticles(section, payload, rows, seq) {\n    if (seq !== loadSeq) return;\n    const grid = section.querySelector('[data-news-v40-grid]');\n    const groups = section.querySelector('[data-news-v40-groups] > div');\n    const items = Array.isArray(payload?.items) ? payload.items.slice(0, TOP_COUNT) : [];\n""",
"""  function pickDiverse(items, limit = TOP_COUNT) {\n    const rows = Array.isArray(items) ? items : [];\n    const chosen = [];\n    const seenSymbols = new Set();\n    const used = new Set();\n    rows.forEach((item, index) => {\n      const symbol = String(item?.symbol || '').toUpperCase();\n      if (!symbol || seenSymbols.has(symbol) || chosen.length >= limit) return;\n      seenSymbols.add(symbol);\n      used.add(index);\n      chosen.push(item);\n    });\n    rows.forEach((item, index) => {\n      if (chosen.length >= limit || used.has(index)) return;\n      chosen.push(item);\n    });\n    return chosen;\n  }\n\n  function renderArticles(section, payload, rows, seq) {\n    if (seq !== loadSeq) return;\n    const grid = section.querySelector('[data-news-v40-grid]');\n    const groups = section.querySelector('[data-news-v40-groups] > div');\n    const items = pickDiverse(payload?.items, TOP_COUNT);\n""", 1)
# Full period must drive the line shape. Downsample across the whole period only when necessary.
old = """  function sparkline(values) {\n    const nums = (Array.isArray(values) ? values : []).map(Number).filter(Number.isFinite).slice(-20);\n    if (nums.length < 2) return '';\n"""
new = """  function sparkline(values) {\n    const source = (Array.isArray(values) ? values : []).map(Number).filter(Number.isFinite);\n    if (source.length < 2) return '';\n    const maxPoints = 40;\n    const nums = source.length <= maxPoints ? source : Array.from({ length: maxPoints }, (_, index) => {\n      const sourceIndex = Math.round(index * (source.length - 1) / (maxPoints - 1));\n      return source[sourceIndex];\n    });\n"""
if old not in text:
    raise SystemExit('sparkline pattern missing')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# 4) News readability: only the lead card is expanded by default; remove whole-document observer.
p = Path('static/js/news_readability_v41_2.js')
text = p.read_text(encoding='utf-8')
text = text.replace("""  function enhanceMarket(details) {\n    if (!details) return;\n    details.open = true;\n""", """  function enhanceMarket(details) {\n    if (!details) return;\n""", 1)
old = """    document.querySelectorAll('.news-v40-card').forEach((card) => {\n      addSummary(card);\n      enhanceMarket(card.querySelector('.news-v40-market'));\n    });\n"""
new = """    document.querySelectorAll('.news-v40-card').forEach((card) => {\n      addSummary(card);\n      const details = card.querySelector('.news-v40-market');\n      if (details && details.dataset.v415DefaultOpen !== '1') {\n        details.dataset.v415DefaultOpen = '1';\n        details.open = card.classList.contains('is-lead');\n      }\n      enhanceMarket(details);\n    });\n"""
if old not in text:
    raise SystemExit('enhanceAll card pattern missing')
text = text.replace(old, new, 1)
old = """  const observer = new MutationObserver(schedule);\n  observer.observe(document.documentElement, { childList: true, subtree: true });\n  document.addEventListener('chartview:v37-news-rendered', schedule);\n  document.addEventListener('DOMContentLoaded', schedule, { once: true });\n  schedule();\n"""
new = """  let newsObserver = null;\n  function attachNewsObserver(attempt = 0) {\n    const section = document.getElementById('home-personal-news-v37');\n    if (section) {\n      if (!newsObserver) {\n        newsObserver = new MutationObserver(schedule);\n        newsObserver.observe(section, { childList: true, subtree: true });\n      }\n      schedule();\n      return;\n    }\n    if (attempt < 30) setTimeout(() => attachNewsObserver(attempt + 1), 300);\n  }\n  document.addEventListener('chartview:v37-news-rendered', () => { attachNewsObserver(); schedule(); });\n  document.addEventListener('DOMContentLoaded', () => attachNewsObserver(), { once: true });\n  attachNewsObserver();\n"""
if old not in text:
    raise SystemExit('global news observer pattern missing')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# 5) Prevent V40 from creating a second market-more control when legacy control already exists.
replace('static/js/release_ui_v40.js',
        "if (!panel || panel.querySelector('[data-v40-market-more]')) return false;",
        "if (!panel || panel.querySelector('[data-v40-market-more]') || panel.querySelector('[data-home23-market-toggle]')) return false;")

# 6) Canonicalize any legacy race into exactly one button and remove the broad document observer.
p = Path('static/js/home_polish_v41_4.js')
text = p.read_text(encoding='utf-8')
start = text.index('  function syncMarketToggle() {')
end = text.index('\n  function decorateWatchlist()', start)
new_func = '''  function syncMarketToggle() {\n    const panel = document.getElementById('home-market-v9');\n    const grid = panel?.querySelector('.home-market-v9-grid');\n    if (!panel || !grid) return false;\n\n    let button = panel.querySelector('[data-v415-market-toggle]');\n    const candidates = [...panel.querySelectorAll('[data-home23-market-toggle], [data-v40-market-more]')];\n    if (!button && candidates.length) {\n      candidates.forEach((node) => node.remove());\n      button = document.createElement('button');\n      button.type = 'button';\n      button.className = 'home23-market-toggle v40-market-more home-v415-market-toggle';\n      button.dataset.home23MarketToggle = '1';\n      button.dataset.v415MarketToggle = '1';\n      grid.insertAdjacentElement('afterend', button);\n      button.addEventListener('click', (event) => {\n        event.preventDefault();\n        event.stopPropagation();\n        const expanded = !panel.classList.contains('home23-expanded');\n        panel.classList.toggle('home23-expanded', expanded);\n        panel.classList.toggle('v40-market-expanded', expanded);\n        syncMarketToggle();\n      });\n    }\n    if (!button) return false;\n\n    panel.querySelectorAll('[data-home23-market-toggle], [data-v40-market-more]').forEach((node) => {\n      if (node !== button) node.remove();\n    });\n    const total = grid.children.length;\n    const hiddenCount = Math.max(0, total - 4);\n    if (!hiddenCount) { button.hidden = true; return true; }\n    button.hidden = false;\n    const expanded = panel.classList.contains('home23-expanded') || panel.classList.contains('v40-market-expanded');\n    panel.classList.toggle('home23-expanded', expanded);\n    panel.classList.toggle('v40-market-expanded', expanded);\n    button.setAttribute('aria-controls', 'home-market-v9-grid');\n    button.setAttribute('aria-expanded', String(expanded));\n    button.innerHTML = `<span>금리 · VIX · 유가 · 환율</span><strong>${expanded ? '접기' : `${hiddenCount}개 더보기`}</strong><i>⌄</i>`;\n    panel.dataset.marketToggleVersion = 'v41.5';\n    return true;\n  }\n'''
text = text[:start] + new_func + text[end:]
old = """  let scheduled = false;\n  const observer = new MutationObserver(() => {\n    if (scheduled) return;\n    scheduled = true;\n    requestAnimationFrame(() => {\n      scheduled = false;\n      sync();\n    });\n  });\n  observer.observe(document.documentElement, { childList: true, subtree: true });\n\n  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync, { once: true });\n  else sync();\n"""
new = """  function boot(attempt = 0) {\n    const ready = syncMarketToggle() | decorateWatchlist();\n    sync();\n    if (!ready && attempt < 30) setTimeout(() => boot(attempt + 1), 300);\n  }\n  document.addEventListener('chartview:v37-news-rendered', () => requestAnimationFrame(sync));\n  document.addEventListener('chartview:watchlist-change', () => requestAnimationFrame(sync));\n  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => boot(), { once: true });\n  else boot();\n"""
if old not in text:
    raise SystemExit('home polish global observer pattern missing')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# 7) Cache-bust the modified client assets through the loader and the loader itself through HTML.
p = Path('static/js/home_watchlist_boot_v32c.js')
text = p.read_text(encoding='utf-8')
for old, new in [
    ('/static/js/personalized_news_v40.js?v=20260913stage12', '/static/js/personalized_news_v40.js?v=20260913v415'),
    ('/static/js/news_readability_v41_2.js?v=20260913v412', '/static/js/news_readability_v41_2.js?v=20260913v415'),
    ('/static/js/release_ui_v40.js?v=20260913stage12', '/static/js/release_ui_v40.js?v=20260913v415'),
    ('/static/js/home_polish_v41_4.js?v=20260913v414', '/static/js/home_polish_v41_4.js?v=20260913v415'),
]:
    if old not in text: raise SystemExit(f'loader version missing: {old}')
    text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

p = Path('templates/index.html')
text = p.read_text(encoding='utf-8')
text = re.sub(r'/static/js/home_watchlist_boot_v32c\.js\?v=[^\"\']+', '/static/js/home_watchlist_boot_v32c.js?v=20260913v415', text)
p.write_text(text, encoding='utf-8')

# Static regression assertions.
assert '"5d": "1d"' in Path('market_service.py').read_text(encoding='utf-8')
assert '_balanced_highlights(all_items, 12)' in news.read_text(encoding='utf-8')
assert 'pickDiverse(payload?.items, TOP_COUNT)' in Path('static/js/personalized_news_v40.js').read_text(encoding='utf-8')
assert '.slice(-20)' not in Path('static/js/personalized_news_v40.js').read_text(encoding='utf-8')
assert 'observer.observe(document.documentElement' not in Path('static/js/news_readability_v41_2.js').read_text(encoding='utf-8')
assert 'observer.observe(document.documentElement' not in Path('static/js/home_polish_v41_4.js').read_text(encoding='utf-8')
assert 'data-v415-market-toggle' in Path('static/js/home_polish_v41_4.js').read_text(encoding='utf-8')
assert '20260913v415' in Path('static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
print('V41.5 consistency patch applied')
