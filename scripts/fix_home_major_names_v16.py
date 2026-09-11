from pathlib import Path

path = Path('static/js/home_brief_v8.js')
text = path.read_text(encoding='utf-8')
old = "    return HOME_MAJOR_STOCKS.map((item) => ({ ...item, ...(map.get(item.symbol) || {}) }));"
new = "    return HOME_MAJOR_STOCKS.map((item) => ({ ...(map.get(item.symbol) || {}), ...item }));"
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('majorRows merge anchor not found')
path.write_text(text, encoding='utf-8')
print('home major labels fixed')
