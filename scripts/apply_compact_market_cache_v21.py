from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'main.py'
JS = ROOT / 'static/js/home_market_v9.js'
CSS = ROOT / 'static/css/home_market_v9.css'
LOADER = ROOT / 'static/js/ux_patch.js'
TEMPLATE = ROOT / 'templates/index.html'


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)


def patch_main():
    text = MAIN.read_text(encoding='utf-8')

    old = '''MARKET_NOW_TICKERS = ["^KS11", "^KQ11", "^GSPC", "^IXIC", "^TNX", "^VIX", "CL=F", "KRW=X"]\n\n@app.get("/api/market-now")\nasync def market_now():\n    """Latest market snapshot using current/latest trade versus the previous close."""\n    fetched = await asyncio.gather(\n        *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in MARKET_NOW_TICKERS],\n        return_exceptions=True,\n    )\n    results, errors = [], []\n    for ticker, row in zip(MARKET_NOW_TICKERS, fetched):\n        if isinstance(row, Exception):\n            errors.append({"ticker": ticker, "message": str(row)})\n            continue\n        if not row:\n            errors.append({"ticker": ticker, "message": "시세 데이터를 가져오지 못했습니다."})\n            continue\n        results.append({\n            "ticker": ticker,\n            "name": row.get("name") or ticker,\n            "price": row.get("price"),\n            "change": row.get("change"),\n            "currency": row.get("currency"),\n            "source": row.get("source") or "Yahoo Chart",\n        })\n    now_kst = datetime.utcnow() + timedelta(hours=9)\n    return {\n        "results": results,\n        "errors": errors,\n        "timestamp": now_kst.strftime("%Y-%m-%d %H:%M:%S"),\n        "date": now_kst.strftime("%Y-%m-%d"),\n        "basis": "previous_close",\n        "source": "Yahoo Finance Chart",\n    }\n'''

    new = '''MARKET_NOW_TICKERS = ["^KS11", "^KQ11", "^GSPC", "^IXIC", "^TNX", "^VIX", "CL=F", "KRW=X"]\nMARKET_NOW_CACHE = {"data": None, "timestamp": 0.0, "refreshing": False}\nMARKET_NOW_TTL = 60\nMARKET_NOW_REFRESH_GUARD = 8\nMARKET_NOW_LOCK = asyncio.Lock()\n\n\nasync def _refresh_market_now(force: bool = False):\n    """Refresh one shared market snapshot while keeping the last successful rows available."""\n    now = time.time()\n    cached = MARKET_NOW_CACHE.get("data")\n    if cached and not force and now - MARKET_NOW_CACHE.get("timestamp", 0) < MARKET_NOW_REFRESH_GUARD:\n        return cached\n\n    async with MARKET_NOW_LOCK:\n        now = time.time()\n        cached = MARKET_NOW_CACHE.get("data")\n        if cached and not force and now - MARKET_NOW_CACHE.get("timestamp", 0) < MARKET_NOW_REFRESH_GUARD:\n            return cached\n\n        MARKET_NOW_CACHE["refreshing"] = True\n        try:\n            previous = {\n                row.get("ticker"): row\n                for row in ((cached or {}).get("results") or [])\n                if isinstance(row, dict) and row.get("ticker")\n            }\n            fetched = await asyncio.gather(\n                *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in MARKET_NOW_TICKERS],\n                return_exceptions=True,\n            )\n            results, errors = [], []\n            for ticker, row in zip(MARKET_NOW_TICKERS, fetched):\n                if isinstance(row, Exception) or not row:\n                    old = previous.get(ticker)\n                    if old:\n                        results.append(old)\n                    errors.append({"ticker": ticker, "message": str(row) if isinstance(row, Exception) else "시세 데이터를 가져오지 못했습니다."})\n                    continue\n                results.append({\n                    "ticker": ticker,\n                    "name": row.get("name") or ticker,\n                    "price": row.get("price"),\n                    "change": row.get("change"),\n                    "currency": row.get("currency"),\n                    "source": row.get("source") or "Yahoo Chart",\n                })\n\n            if not results and cached:\n                return cached\n\n            now_kst = datetime.utcnow() + timedelta(hours=9)\n            data = {\n                "results": results,\n                "errors": errors,\n                "timestamp": now_kst.strftime("%Y-%m-%d %H:%M:%S"),\n                "date": now_kst.strftime("%Y-%m-%d"),\n                "basis": "previous_close",\n                "source": "Yahoo Finance Chart",\n            }\n            MARKET_NOW_CACHE["data"] = data\n            MARKET_NOW_CACHE["timestamp"] = time.time()\n            return data\n        finally:\n            MARKET_NOW_CACHE["refreshing"] = False\n\n\n@app.get("/api/market-now")\nasync def market_now(fresh: bool = False):\n    """Return shared market cache immediately; revalidate stale data in the background."""\n    data = MARKET_NOW_CACHE.get("data")\n    if fresh:\n        try:\n            data = await _refresh_market_now(force=True) or data\n        except Exception as exc:\n            print(f"[MARKET NOW] foreground refresh failed: {exc}")\n    elif not data:\n        try:\n            data = await _refresh_market_now(force=True)\n        except Exception as exc:\n            print(f"[MARKET NOW] first refresh failed: {exc}")\n    else:\n        age = time.time() - MARKET_NOW_CACHE.get("timestamp", 0)\n        if age >= MARKET_NOW_TTL and not MARKET_NOW_CACHE.get("refreshing"):\n            asyncio.create_task(_refresh_market_now(force=False))\n\n    payload = dict(data or {"results": [], "errors": []})\n    payload["cacheAgeSec"] = round(max(0.0, time.time() - MARKET_NOW_CACHE.get("timestamp", 0)), 1)\n    payload["refreshing"] = bool(MARKET_NOW_CACHE.get("refreshing"))\n    payload["cacheMode"] = "stale-while-revalidate"\n    return payload\n'''
    text = replace_once(text, old, new, 'market endpoint')

    startup_old = '''        await asyncio.wait_for(_refresh_home_snapshot(force=True), timeout=12)\n        print("[HOME] shared snapshot warmed")\n'''
    startup_new = '''        await asyncio.wait_for(_refresh_home_snapshot(force=True), timeout=12)\n        try:\n            await asyncio.wait_for(_refresh_market_now(force=True), timeout=10)\n            print("[MARKET NOW] shared snapshot warmed")\n        except Exception as market_exc:\n            print(f"[MARKET NOW] warmup deferred: {market_exc}")\n        print("[HOME] shared snapshot warmed")\n'''
    text = replace_once(text, startup_old, startup_new, 'startup market warm')
    MAIN.write_text(text, encoding='utf-8')


def patch_js():
    text = JS.read_text(encoding='utf-8')

    old_insert = '''    home.appendChild(panel);\n    return panel;\n'''
    new_insert = '''    const anchor = document.getElementById('home-v8-body');\n    if (anchor && anchor.parentElement === home) home.insertBefore(panel, anchor);\n    else home.prepend(panel);\n    return panel;\n'''
    text = replace_once(text, old_insert, new_insert, 'market top placement')

    old_load = '''  async function loadMarket(force = false) {\n    if (!isHomeActive()) return;\n    const panel = ensurePanel();\n    if (!panel) return;\n    if (!force && Date.now() - lastLoadedAt < 45_000) return;\n\n    const seq = ++marketLoadSeq;\n    try {\n      const response = await fetch('/api/market-now', { cache: 'no-store' });\n      if (!response.ok) throw new Error(`market HTTP ${response.status}`);\n      const data = await response.json();\n      if (seq !== marketLoadSeq) return;\n\n      const rows = new Map((data.results || []).map((row) => [row.ticker, row]));\n      MARKET_ITEMS.forEach((item) => {\n        const node = panel.querySelector(`[data-market-symbol="${CSS.escape(item.symbol)}"]`);\n        if (!node) return;\n        const row = rows.get(item.symbol);\n        const change = formatChange(item, row);\n        node.classList.remove('is-loading');\n        node.innerHTML = `\n          <span>${item.label}</span>\n          <strong>${formatValue(item, row)}</strong>\n          <small class="${change.dir}">${change.text}</small>`;\n      });\n\n      const time = panel.querySelector('#home-market-v9-time');\n      if (time) time.textContent = `${formatCheckedAt(data)} 기준`;\n      lastLoadedAt = Date.now();\n    } catch (error) {\n      console.warn('home market snapshot failed', error);\n      const time = panel.querySelector('#home-market-v9-time');\n      if (time) time.textContent = '일부 데이터 확인 필요';\n    }\n  }\n'''

    new_load = '''  function paintMarket(panel, data) {\n    if (!panel || !data) return false;\n    const rows = new Map((data.results || []).map((row) => [row.ticker, row]));\n    let painted = 0;\n    MARKET_ITEMS.forEach((item) => {\n      const node = panel.querySelector(`[data-market-symbol="${CSS.escape(item.symbol)}"]`);\n      if (!node) return;\n      const row = rows.get(item.symbol);\n      if (!row) return;\n      const change = formatChange(item, row);\n      node.classList.remove('is-loading');\n      node.innerHTML = `\n        <span>${item.label}</span>\n        <strong>${formatValue(item, row)}</strong>\n        <small class="${change.dir}">${change.text}</small>`;\n      painted += 1;\n    });\n    const time = panel.querySelector('#home-market-v9-time');\n    if (time && painted) time.textContent = `${formatCheckedAt(data)} 기준`;\n    return painted > 0;\n  }\n\n  function saveMarketLocal(data) {\n    try { localStorage.setItem('chartview-market-now-v21', JSON.stringify(data)); } catch (_) {}\n  }\n\n  function readMarketLocal() {\n    try {\n      const raw = localStorage.getItem('chartview-market-now-v21');\n      return raw ? JSON.parse(raw) : null;\n    } catch (_) { return null; }\n  }\n\n  async function loadMarket(force = false) {\n    if (!isHomeActive()) return;\n    const panel = ensurePanel();\n    if (!panel) return;\n    if (!force && Date.now() - lastLoadedAt < 45_000) return;\n\n    const seq = ++marketLoadSeq;\n    try {\n      const response = await fetch(`/api/market-now${force ? '?fresh=1' : ''}`, { cache: 'no-store' });\n      if (!response.ok) throw new Error(`market HTTP ${response.status}`);\n      const data = await response.json();\n      if (seq !== marketLoadSeq) return;\n      if (paintMarket(panel, data)) {\n        saveMarketLocal(data);\n        lastLoadedAt = Date.now();\n      }\n    } catch (error) {\n      console.warn('home market snapshot failed', error);\n      const time = panel.querySelector('#home-market-v9-time');\n      if (time && !readMarketLocal()) time.textContent = '일부 데이터 확인 필요';\n    }\n  }\n'''
    text = replace_once(text, old_load, new_load, 'market local cache')

    old_init = '''      if (ensurePanel()) {\n        clearInterval(timer);\n        loadMarket(true);\n        startRefreshLoop();\n'''
    new_init = '''      const panel = ensurePanel();\n      if (panel) {\n        clearInterval(timer);\n        const local = readMarketLocal();\n        if (local) paintMarket(panel, local);\n        loadMarket(false);\n        setTimeout(() => loadMarket(true), 450);\n        startRefreshLoop();\n'''
    text = replace_once(text, old_init, new_init, 'market instant init')
    JS.write_text(text, encoding='utf-8')


def patch_css():
    text = CSS.read_text(encoding='utf-8')
    marker = '/* HOME MARKET V21: compact top strip */'
    if marker not in text:
        text += '''\n\n/* HOME MARKET V21: compact top strip */\n.home-market-v9{margin:4px 0 12px;padding:10px 12px 9px;border-radius:17px}\n.home-market-v9-head{align-items:center;margin-bottom:8px}\n.home-market-v9-head strong{font-size:17px}\n.home-market-v9-kicker{font-size:9px}\n#home-market-v9-time{font-size:10px}\n.home-market-v9-grid{gap:6px}\n.home-market-v9-item{padding:8px 9px;border-radius:11px}\n.home-market-v9-item>span{margin-bottom:2px;font-size:9.5px}\n.home-market-v9-item>strong{margin-bottom:1px;font-size:14px}\n.home-market-v9-item>small{font-size:9.5px}\n.home-market-v9-foot{margin-top:7px;font-size:9px}\n\n@media(max-width:720px){\n  .home-market-v9{margin:4px 10px 10px;padding:10px 10px 8px;border-radius:16px}\n  .home-market-v9-head{margin-bottom:7px}\n  .home-market-v9-head>div{gap:6px}\n  .home-market-v9-head strong{font-size:16px}\n  .home-market-v9-grid{display:flex;grid-template-columns:none;gap:6px;overflow-x:auto;padding-bottom:2px;scrollbar-width:none;scroll-snap-type:x proximity}\n  .home-market-v9-grid::-webkit-scrollbar{display:none}\n  .home-market-v9-item{flex:0 0 108px;min-height:64px;padding:7px 8px;scroll-snap-align:start}\n  .home-market-v9-item>span{font-size:9px}\n  .home-market-v9-item>strong{font-size:13.5px}\n  .home-market-v9-item>small{font-size:9px}\n  .home-market-v9-foot{display:none}\n}\n'''
    CSS.write_text(text, encoding='utf-8')


def bust_cache():
    text = LOADER.read_text(encoding='utf-8')
    text = text.replace('/static/css/home_market_v9.css?v=20260911v10', '/static/css/home_market_v9.css?v=20260911v21')
    text = text.replace('/static/js/home_market_v9.js?v=20260911v16', '/static/js/home_market_v9.js?v=20260911v21')
    LOADER.write_text(text, encoding='utf-8')

    text = TEMPLATE.read_text(encoding='utf-8')
    text = text.replace('/static/js/ux_patch.js?v=20260911v19', '/static/js/ux_patch.js?v=20260911v21')
    text = text.replace('/static/js/ux_patch.js?v=20260911v20', '/static/js/ux_patch.js?v=20260911v21')
    TEMPLATE.write_text(text, encoding='utf-8')


def main():
    patch_main()
    patch_js()
    patch_css()
    bust_cache()
    print('compact cached market V21 applied')


if __name__ == '__main__':
    main()
