from pathlib import Path

path = Path('main.py')
text = path.read_text(encoding='utf-8')

import_anchor = 'from consensus_service import fetch_consensus\n'
import_line = 'from news_service_v37 import router as news_router_v37\n'
if import_line not in text:
    if import_anchor not in text:
        raise SystemExit('consensus import anchor not found')
    text = text.replace(import_anchor, import_anchor + import_line, 1)

app_anchor = 'app = FastAPI(title="주식 비교 차트", version="1.0.0")\n'
include_block = '\n# V37 personalized watchlist news router.\napp.include_router(news_router_v37)\n'
if 'app.include_router(news_router_v37)' not in text:
    if app_anchor not in text:
        raise SystemExit('FastAPI app anchor not found')
    text = text.replace(app_anchor, app_anchor + include_block, 1)

path.write_text(text, encoding='utf-8')
print('V37 main.py router patch applied')
