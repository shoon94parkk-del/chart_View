from pathlib import Path

# ---------- market_service.py: lightweight quote/history helpers ----------
p = Path('market_service.py')
text = p.read_text(encoding='utf-8')

if '_quote_cache:' not in text:
    anchor = '_valuation_cache: dict[str, tuple[float, dict[str, Any]]] = {}\n'
    if anchor not in text:
        raise SystemExit('valuation cache anchor missing')
    text = text.replace(anchor, anchor + '_quote_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}\n', 1)

if 'def fetch_quote_snapshot(' not in text:
    anchor = '\ndef fetch_valuation_snapshot(symbol: str) -> dict[str, Any]:\n'
    if anchor not in text:
        raise SystemExit('valuation function anchor missing')
    helper = '''

def fetch_quote_snapshot(symbol: str) -> dict[str, Any] | None:
    """Fast current quote for heatmaps; uses Yahoo chart only, never crumb/info."""
    symbol = symbol.strip().upper()
    if not symbol:
        return None
    now = time.time()
    with _cache_lock:
        cached = _quote_cache.get(symbol)
        if cached and now - cached[0] < 60:
            return cached[1]
    try:
        result = _chart_result(symbol, period="5d", interval="1d")
        meta = result.get("meta", {})
        closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
        good = [float(v) for v in closes if v is not None and float(v) > 0]
        if not good:
            value = None
        else:
            current = _positive(meta.get("regularMarketPrice")) or good[-1]
            previous = (
                _positive(meta.get("chartPreviousClose"))
                or _positive(meta.get("previousClose"))
                or (good[-2] if len(good) > 1 else None)
            )
            change = ((current - previous) / previous * 100) if previous else 0.0
            detail = _local_detail_cache().get(symbol, {})
            value = {
                "ticker": symbol,
                "name": _local_names().get(symbol) or meta.get("shortName") or meta.get("longName") or detail.get("shortName") or symbol,
                "price": round(float(current), 2),
                "change": round(float(change), 2),
                "marketCap": _number(detail.get("marketCap")),
                "currency": meta.get("currency") or detail.get("currency"),
                "source": "Yahoo Chart",
            }
    except Exception as exc:
        print(f"[MarketData] quote failed {symbol}: {exc}")
        value = None
    with _cache_lock:
        _quote_cache[symbol] = (now, value)
    return value


def fetch_history_series(symbol: str, period: str = "6mo") -> list[dict[str, Any]]:
    """Daily close history using the same crumb-free chart endpoint."""
    symbol = symbol.strip().upper()
    result = _chart_result(symbol, period=period, interval="1d")
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        value = _number(close)
        if value is None or value <= 0:
            continue
        date = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append({"time": date, "value": round(value, 4)})
    return rows
'''
    text = text.replace(anchor, helper + anchor, 1)

p.write_text(text, encoding='utf-8')

# ---------- main.py ----------
p = Path('main.py')
main = p.read_text(encoding='utf-8')
main = main.replace('from market_service import fetch_compare_stock, fetch_valuation_snapshot',
                    'from market_service import fetch_compare_stock, fetch_valuation_snapshot, fetch_quote_snapshot, fetch_history_series')

# Prefer the already-generated local screener universe before making KIND network calls.
if '# local-screener-universe-v4' not in main:
    needle = '''    try:\n        # KRX 종목 리스트를 krx.co.kr에서 가져오기\n        headers = {"User-Agent": "Mozilla/5.0"}\n        \n        all_stocks = []\n'''
    replacement = '''    try:\n        # local-screener-universe-v4: GitHub Actions가 만든 전체 종목 JSON을 먼저 사용.\n        # Render cold start에서 KIND를 다시 다운로드하던 수초 지연을 제거한다.\n        try:\n            import json as _json\n            local_path = os.path.join(os.path.dirname(__file__), "static", "data", "screener.json")\n            with open(local_path, "r", encoding="utf-8") as f:\n                payload = _json.load(f)\n            local_rows = []\n            for row in payload.get("stocks", []):\n                code = str(row.get("code") or "").zfill(6)\n                name = str(row.get("name") or "").strip()\n                market = str(row.get("market") or "")\n                if code and name and market in ("KOSPI", "KOSDAQ"):\n                    local_rows.append({\n                        "code": code, "name": name, "market": market,\n                        "suffix": ".KS" if market == "KOSPI" else ".KQ"\n                    })\n            if local_rows:\n                KRX_STOCK_LIST = local_rows\n                KRX_CACHE_TIME = time.time()\n                return KRX_STOCK_LIST\n        except Exception as e:\n            print(f"[KRX] Local screener universe unavailable: {e}")\n\n        # Fallback: KIND bulk download\n        headers = {"User-Agent": "Mozilla/5.0"}\n        all_stocks = []\n'''
    if needle not in main:
        raise SystemExit('KRX loader anchor missing')
    main = main.replace(needle, replacement, 1)

# Replace first search endpoint with one unified, network-free autocomplete path.
first = main.index('@app.get("/api/search")')
first_end = main.index('\ndef get_korean_stock_name', first)
unified_search = '''@app.get("/api/search")
async def search_stocks(q: str):
    """Unified fast search: local KRX universe + local aliases, no yfinance.info."""
    query = (q or "").strip()
    if not query:
        return {"results": []}

    aliases = {
        "삼전": "삼성전자", "하닉": "SK하이닉스", "삼바": "삼성바이오로직스",
        "엘전": "LG전자", "현차": "현대차", "네이버": "NAVER",
    }
    lookup = aliases.get(query.lower(), query)
    ql = query.lower()
    ll = lookup.lower()
    found = {}

    def put(symbol, name, kind="GLOBAL", code=None, market=None, score=50):
        old = found.get(symbol)
        row = {"symbol": symbol, "name": name, "type": kind, "score": score}
        if code: row["code"] = code
        if market: row["market"] = market
        if old is None or score < old["score"]:
            found[symbol] = row

    # Small hand-curated alias DB is instant and also resolves Korean names such as 애플/테슬라.
    for stock in STOCK_DATABASE:
        symbol = stock["symbol"]
        name = stock["name"]
        blob = f"{symbol} {name} {stock.get('keywords', '')}".lower()
        if ql == symbol.lower() or ql == name.lower() or ll == symbol.lower() or ll == name.lower():
            put(symbol, name, "LOCAL", score=0)
        elif name.lower().startswith(ql) or symbol.lower().startswith(ql):
            put(symbol, name, "LOCAL", score=1)
        elif ql in blob or ll in blob:
            put(symbol, name, "LOCAL", score=3)

    # Full KRX lookup is read from local screener.json; no network on normal operation.
    has_korean = any('\uac00' <= c <= '\ud7a3' for c in lookup)
    is_code = lookup.isdigit() and len(lookup) == 6
    if has_korean or is_code:
        for stock in load_krx_stock_list():
            name = stock["name"]
            code = stock["code"]
            if (is_code and code == lookup) or (has_korean and lookup in name):
                score = 0 if (name == lookup or code == lookup) else (1 if name.startswith(lookup) else 2)
                put(f"{code}{stock.get('suffix', '.KS')}", name, "KRX", code, stock.get("market"), score)

    results = sorted(found.values(), key=lambda x: (x["score"], x["name"]))[:10]
    for row in results:
        row.pop("score", None)

    # Unknown ASCII ticker: add immediately and let /api/compare validate it.
    if not results and all(c.isalnum() or c in '.^-=' for c in lookup) and not is_code:
        results = [{"symbol": lookup.upper(), "name": lookup.upper(), "type": "DIRECT"}]

    return {"results": results}

'''
main = main[:first] + unified_search + main[first_end+1:]

# Remove the duplicate second /api/search route entirely.
second = main.find('@app.get("/api/search")', first + len(unified_search))
if second != -1:
    second_end = main.index('@app.get("/api/heatmap")', second)
    main = main[:second] + main[second_end:]

# Replace heatmap's yfinance.info fanout with crumb-free chart snapshots.
heat_start = main.index('@app.get("/api/heatmap")')
heat_end = main.index('\ndef compute_net_liquidity', heat_start)
heatmap = '''@app.get("/api/heatmap")
async def heatmap_data():
    """Heatmap snapshots via the lightweight chart endpoint (no yfinance.info)."""
    heatmap_tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
        "JPM", "V", "MA", "UNH", "JNJ", "LLY", "XOM", "AVGO",
        "005930.KS", "000660.KS", "035420.KS", "035720.KS", "005380.KS"
    ]
    fetched = await asyncio.gather(
        *[asyncio.to_thread(fetch_quote_snapshot, t) for t in heatmap_tickers],
        return_exceptions=True,
    )
    results = []
    for ticker, row in zip(heatmap_tickers, fetched):
        if isinstance(row, Exception) or not row:
            continue
        results.append({
            "ticker": ticker,
            "name": row.get("name") or ticker,
            "change": row.get("change", 0),
            "price": row.get("price"),
            "marketCap": row.get("marketCap") or 0,
        })
    return {"results": results}

'''
main = main[:heat_start] + heatmap + main[heat_end+1:]

# Replace Yahoo macro fallbacks/history with our chart helper to avoid yfinance cookie/crumb paths.
old_fallback = '''            stock = yf.Ticker(fallback_sym)\n            hist = stock.history(period="6mo")\n            if hist.empty: \n                return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}\n            \n            current = hist['Close'].iloc[-1]\n            prev = hist['Close'].iloc[-2]\n            change = ((current - prev) / prev) * 100\n            chart_data = [{"time": t.strftime("%Y-%m-%d"), "value": round(v, 2)} for t, v in hist['Close'].items()]'''
new_fallback = '''            chart_data = fetch_history_series(fallback_sym, "6mo")\n            if len(chart_data) < 2:\n                return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}\n            current = chart_data[-1]["value"]\n            prev = chart_data[-2]["value"]\n            change = ((current - prev) / prev) * 100 if prev else 0.0'''
if old_fallback in main:
    main = main.replace(old_fallback, new_fallback, 1)
else:
    raise SystemExit('macro fallback yfinance anchor missing')

old_indicator = '''            stock = yf.Ticker(symbol)\n            hist = stock.history(period="6mo")\n            if hist.empty: \n                return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}\n\n            current, prev = hist['Close'].iloc[-1], hist['Close'].iloc[-2]\n            change = ((current - prev) / prev) * 100\n            chart_data = [{"time": t.strftime("%Y-%m-%d"), "value": round(v, 2)} for t, v in hist['Close'].items()]'''
new_indicator = '''            chart_data = fetch_history_series(symbol, "6mo")\n            if len(chart_data) < 2:\n                return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}\n            current, prev = chart_data[-1]["value"], chart_data[-2]["value"]\n            change = ((current - prev) / prev) * 100 if prev else 0.0'''
if old_indicator in main:
    main = main.replace(old_indicator, new_indicator, 1)
else:
    raise SystemExit('macro indicator yfinance anchor missing')

# CORS: wildcard + credentials is unsafe/inconsistent. Same-origin Render needs no wildcard.
main = main.replace('        "*",  # 개발용 (프로덕션에서는 제거 권장)\n',
                    '        "https://chart-view-bsg6.onrender.com",\n        "http://localhost:8080",\n        "http://127.0.0.1:8080",\n')

# Clean duplicated import; keep yfinance import for now only if another path still references yf.
main = main.replace('from fastapi.responses import JSONResponse, StreamingResponse\nfrom fastapi.staticfiles import StaticFiles\nfrom fastapi.templating import Jinja2Templates\nfrom fastapi.responses import JSONResponse\n',
                    'from fastapi.responses import JSONResponse, StreamingResponse\nfrom fastapi.staticfiles import StaticFiles\nfrom fastapi.templating import Jinja2Templates\n')

# If no yfinance use remains, remove import to reduce startup/import cost.
if 'yf.' not in main:
    main = main.replace('import yfinance as yf\n', '')

p.write_text(main, encoding='utf-8')
compile(main, 'main.py', 'exec')
compile(text, 'market_service.py', 'exec')
print('data path v4 patch complete')
