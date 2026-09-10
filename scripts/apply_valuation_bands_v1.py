from pathlib import Path

root = Path(__file__).resolve().parents[1]

# main.py: import service + endpoint
main = root / 'main.py'
text = main.read_text(encoding='utf-8')
old_import = 'from market_service import fetch_compare_stock, fetch_valuation_snapshot, fetch_quote_snapshot, fetch_history_series\n'
new_import = old_import + 'from valuation_band_service import fetch_valuation_bands\n'
if 'from valuation_band_service import fetch_valuation_bands' not in text:
    if old_import not in text:
        raise SystemExit('main.py import anchor not found')
    text = text.replace(old_import, new_import, 1)

endpoint = '''\n\n@app.get("/api/valuation-band")\nasync def valuation_band_data(ticker: str, years: int = 3):\n    symbol = (ticker or "").strip().upper()\n    if not symbol:\n        return JSONResponse({"error": "종목을 입력해주세요"}, status_code=400)\n    try:\n        data = await asyncio.to_thread(fetch_valuation_bands, symbol, years)\n        return data\n    except Exception as exc:\n        print(f"[ValuationBand] {symbol} failed: {exc}")\n        return JSONResponse(\n            {"error": "역사적 밸류에이션 데이터를 계산하지 못했습니다.", "ticker": symbol},\n            status_code=503,\n        )\n'''
if '@app.get("/api/valuation-band")' not in text:
    anchor = '\n\nif __name__ == "__main__":\n'
    if anchor not in text:
        raise SystemExit('main.py endpoint anchor not found')
    text = text.replace(anchor, endpoint + anchor, 1)
main.write_text(text, encoding='utf-8')

# index.html: load band feature with explicit cache bust.
index = root / 'templates' / 'index.html'
text = index.read_text(encoding='utf-8')
script = '    <script src="/static/js/valuation_bands.js?v=20260911v1"></script>\n'
if 'valuation_bands.js' not in text:
    anchor = '    <script src="/static/js/fwdper.js?v=20260911v1"></script>\n'
    if anchor not in text:
        raise SystemExit('index script anchor not found')
    text = text.replace(anchor, anchor + script, 1)
index.write_text(text, encoding='utf-8')

print('valuation bands integration applied')
