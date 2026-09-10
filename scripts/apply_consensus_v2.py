from pathlib import Path

root = Path(__file__).resolve().parents[1]

# main.py: import service and expose endpoint.
main = root / 'main.py'
text = main.read_text(encoding='utf-8')
import_anchor = 'from valuation_band_service import fetch_valuation_bands\n'
if 'from consensus_service import fetch_consensus' not in text:
    if import_anchor not in text:
        raise SystemExit('main import anchor not found')
    text = text.replace(import_anchor, import_anchor + 'from consensus_service import fetch_consensus\n', 1)

endpoint = '''\n\n@app.get("/api/consensus")\nasync def consensus_data(ticker: str):\n    symbol = (ticker or "").strip().upper()\n    if not symbol:\n        return JSONResponse({"error": "종목을 입력해주세요"}, status_code=400)\n    try:\n        return await asyncio.to_thread(fetch_consensus, symbol)\n    except Exception as exc:\n        print(f"[Consensus] {symbol} failed: {exc}")\n        return JSONResponse(\n            {"error": "애널리스트 컨센서스 데이터를 불러오지 못했습니다.", "ticker": symbol},\n            status_code=503,\n        )\n'''
if '@app.get("/api/consensus")' not in text:
    anchor = '\n\nif __name__ == "__main__":\n'
    if anchor not in text:
        raise SystemExit('main endpoint anchor not found')
    text = text.replace(anchor, endpoint + anchor, 1)
main.write_text(text, encoding='utf-8')

# index.html: include the phase-2 UI with a cache-busting version.
index = root / 'templates' / 'index.html'
text = index.read_text(encoding='utf-8')
script = '    <script src="/static/js/consensus_v2.js?v=20260911v1"></script>\n'
if 'consensus_v2.js' not in text:
    anchor = '</body>'
    if anchor not in text:
        raise SystemExit('index body anchor not found')
    text = text.replace(anchor, script + anchor, 1)
index.write_text(text, encoding='utf-8')

# live-smoke: make the new feature part of production regression coverage.
smoke = root / '.github' / 'workflows' / 'live-smoke.yml'
text = smoke.read_text(encoding='utf-8')
if "      - 'consensus_service.py'\n" not in text:
    text = text.replace("      - 'valuation_band_service.py'\n", "      - 'valuation_band_service.py'\n      - 'consensus_service.py'\n", 1)
if "      - 'static/data/consensus_cache.json'\n" not in text:
    text = text.replace("      - 'static/data/valuation_cache.json'\n", "      - 'static/data/valuation_cache.json'\n      - 'static/data/consensus_cache.json'\n      - 'static/data/consensus_history.json'\n", 1)
if "grep -q '/static/js/consensus_v2.js?v=20260911v1'" not in text:
    old = "              && grep -q '/static/js/valuation_bands.js?v=20260911v1' /tmp/home.html; then"
    new = "              && grep -q '/static/js/valuation_bands.js?v=20260911v1' /tmp/home.html \\\n              && grep -q '/static/js/consensus_v2.js?v=20260911v1' /tmp/home.html; then"
    if old not in text:
        raise SystemExit('live smoke build marker anchor not found')
    text = text.replace(old, new, 1)
if 'curl -fsSL "$BASE/static/js/consensus_v2.js?v=20260911v1"' not in text:
    anchor = '          curl -fsSL "$BASE/static/js/valuation_bands.js?v=20260911v1" -o /tmp/bands.js\n'
    text = text.replace(anchor, anchor + '          curl -fsSL "$BASE/static/js/consensus_v2.js?v=20260911v1" -o /tmp/consensus.js\n', 1)
    text = text.replace("          grep -q '역사적 밸류에이션 밴드' /tmp/bands.js\n", "          grep -q '역사적 밸류에이션 밴드' /tmp/bands.js\n          grep -q 'EPS · 매출 컨센서스 추세' /tmp/consensus.js\n", 1)

if "echo 'Analyst consensus:'" not in text:
    marker = '          curl -fsSL "$BASE/api/heatmap" -o /tmp/heatmap.json\n'
    block = '''          echo 'Analyst consensus:'\n          for t in AAPL NVDA 005930.KS 000660.KS; do\n            curl -fsSL --get --data-urlencode "ticker=$t" "$BASE/api/consensus" -o "/tmp/cons-$t.json"\n          done\n          python - <<'PY'\n          import json\n          for t in ('AAPL','NVDA','005930.KS','000660.KS'):\n              d=json.load(open(f'/tmp/cons-{t}.json'))\n              for p in ('0q','+1q','0y','+1y'):\n                  row=d.get('periods',{}).get(p) or {}\n                  assert (row.get('earnings') or {}).get('avg') is not None, (t,p,'eps')\n                  assert (row.get('revenue') or {}).get('avg') is not None, (t,p,'revenue')\n              annual=d['periods']['0y']\n              assert (annual.get('epsTrend') or {}).get('90daysAgo') is not None, (t,'90d trend')\n              print('consensus OK',t,'EPS',annual['earnings']['avg'],'Revenue',annual['revenue']['avg'],'mode',d.get('cacheMode'))\n          PY\n\n'''
    if marker not in text:
        raise SystemExit('live smoke consensus insertion anchor not found')
    text = text.replace(marker, block + marker, 1)
smoke.write_text(text, encoding='utf-8')

print('phase-2 consensus integration applied')
