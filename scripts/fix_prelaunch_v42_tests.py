from pathlib import Path
p=Path('tests/test_v37_personalized_news.py')
text=p.read_text(encoding='utf-8')
text=text.replace('assert "/static/js/personalized_news_v40.js?v=20260913v415" in boot', 'assert "/static/js/personalized_news_v40.js?v=" in boot')
p.write_text(text,encoding='utf-8')
print('updated remaining frozen V40 asset assertion')
