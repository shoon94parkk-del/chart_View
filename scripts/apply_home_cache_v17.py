from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'main.py'
HOME_JS = ROOT / 'static/js/home_brief_v8.js'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f'{label}: target not found')
    return text.replace(old, new, 1)


def patch_main() -> None:
    text = MAIN.read_text(encoding='utf-8')

    cache_anchor = '''STOCK_INFO_CACHE = {}  # {ticker: {"name": str, "timestamp": float}}\nCACHE_EXPIRE = 3600 * 6  # 6시간 캐시\n'''
    cache_new = '''STOCK_INFO_CACHE = {}  # {ticker: {"name": str, "timestamp": float}}\nCACHE_EXPIRE = 3600 * 6  # 6시간 캐시\n\n# HOME V17 shared stale-while-revalidate snapshot.\n# One successful load is reused by every visitor; refresh happens in the background.\nHOME_SNAPSHOT_CACHE = {"data": None, "timestamp": 0.0, "refreshing": False}\nHOME_SNAPSHOT_TTL = 60\nHOME_SNAPSHOT_REFRESH_GUARD = 8\nHOME_MAJOR_TICKERS = [\n    "005930.KS", "000660.KS", "NVDA", "AAPL",\n    "MSFT", "META", "TSLA", "GOOGL",\n]\nHOME_SNAPSHOT_LOCK = asyncio.Lock()\n'''
    text = replace_once(text, cache_anchor, cache_new, 'home cache globals')

    startup_old = '''@app.on_event("startup")\nasync def startup_event():\n    """서버 시작 시 Self-Ping 백그라운드 스레드 시작"""\n    ping_thread = threading.Thread(target=self_ping_worker, daemon=True)\n    ping_thread.start()\n'''
    startup_new = '''@app.on_event("startup")\nasync def startup_event():\n    """Start keep-alive and warm the shared Home snapshot before traffic arrives."""\n    ping_thread = threading.Thread(target=self_ping_worker, daemon=True)\n    ping_thread.start()\n    try:\n        _seed_home_snapshot_from_disk()\n        await asyncio.wait_for(_refresh_home_snapshot(force=True), timeout=12)\n        print("[HOME] shared snapshot warmed")\n    except Exception as exc:\n        # The disk seed still lets Home render immediately even if Yahoo is temporarily slow.\n        print(f"[HOME] warmup deferred: {exc}")\n'''
    text = replace_once(text, startup_old, startup_new, 'startup warmup')

    insert_anchor = '''\n\n@app.get("/api/fwd-per")\n@app.get("/api/valuation")\nasync def valuation_data(tickers: str):\n'''
    snapshot_code = '''

def _seed_home_snapshot_from_disk():
    """Best-effort cold-start seed from the committed daily valuation cache."""
    if HOME_SNAPSHOT_CACHE.get("data"):
        return HOME_SNAPSHOT_CACHE["data"]
    results = []
    try:
        import json as _json
        cache_path = os.path.join(os.path.dirname(__file__), "static", "data", "valuation_cache.json")
        with open(cache_path, "r", encoding="utf-8") as f:
            quotes = (_json.load(f).get("quotes") or {})
        for ticker in HOME_MAJOR_TICKERS:
            row = quotes.get(ticker) or {}
            price = row.get("regularMarketPrice")
            if price is None:
                price = row.get("price")
            change = row.get("regularMarketChangePercent")
            if change is None:
                change = row.get("change")
            if price is None:
                continue
            results.append({
                "ticker": ticker,
                "name": row.get("shortName") or ticker,
                "price": price,
                "change": change,
                "marketCap": row.get("marketCap") or 0,
            })
    except Exception as exc:
        print(f"[HOME] disk seed unavailable: {exc}")

    if results:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        HOME_SNAPSHOT_CACHE["data"] = {
            "heatmap": {"results": results},
            "macro": MACRO_CACHE.get("data"),
            "generatedAt": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "disk-seed",
        }
        HOME_SNAPSHOT_CACHE["timestamp"] = time.time()
    return HOME_SNAPSHOT_CACHE.get("data")


async def _refresh_home_snapshot(force: bool = False):
    """Refresh the shared snapshot once, preserving old rows when a provider is partial."""
    now = time.time()
    cached = HOME_SNAPSHOT_CACHE.get("data")
    if cached and not force and now - HOME_SNAPSHOT_CACHE.get("timestamp", 0) < HOME_SNAPSHOT_REFRESH_GUARD:
        return cached

    async with HOME_SNAPSHOT_LOCK:
        now = time.time()
        cached = HOME_SNAPSHOT_CACHE.get("data")
        if cached and not force and now - HOME_SNAPSHOT_CACHE.get("timestamp", 0) < HOME_SNAPSHOT_REFRESH_GUARD:
            return cached

        HOME_SNAPSHOT_CACHE["refreshing"] = True
        try:
            previous_rows = {
                row.get("ticker"): row
                for row in ((cached or {}).get("heatmap", {}).get("results") or [])
                if isinstance(row, dict) and row.get("ticker")
            }
            fetched = await asyncio.gather(
                *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in HOME_MAJOR_TICKERS],
                return_exceptions=True,
            )
            results = []
            for ticker, row in zip(HOME_MAJOR_TICKERS, fetched):
                if isinstance(row, Exception) or not row:
                    old = previous_rows.get(ticker)
                    if old:
                        results.append(old)
                    continue
                results.append({
                    "ticker": ticker,
                    "name": row.get("name") or ticker,
                    "change": row.get("change"),
                    "price": row.get("price"),
                    "marketCap": row.get("marketCap") or 0,
                })

            if not results and cached:
                return cached

            macro_payload = None
            try:
                macro_candidate = await macro_data()
                if not isinstance(macro_candidate, JSONResponse):
                    macro_payload = macro_candidate
            except Exception as exc:
                print(f"[HOME] macro snapshot refresh failed: {exc}")
            if macro_payload is None and cached:
                macro_payload = cached.get("macro")

            now_kst = datetime.utcnow() + timedelta(hours=9)
            data = {
                "heatmap": {"results": results},
                "macro": macro_payload,
                "generatedAt": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "shared-memory-swr",
            }
            HOME_SNAPSHOT_CACHE["data"] = data
            HOME_SNAPSHOT_CACHE["timestamp"] = time.time()
            return data
        finally:
            HOME_SNAPSHOT_CACHE["refreshing"] = False


@app.get("/api/home-snapshot")
async def home_snapshot(fresh: bool = False):
    """Return the last successful Home snapshot immediately and revalidate behind it."""
    data = HOME_SNAPSHOT_CACHE.get("data") or _seed_home_snapshot_from_disk()
    if fresh:
        try:
            data = await _refresh_home_snapshot(force=True) or data
        except Exception as exc:
            print(f"[HOME] foreground refresh failed: {exc}")
    elif not data:
        try:
            data = await _refresh_home_snapshot(force=True)
        except Exception as exc:
            print(f"[HOME] first refresh failed: {exc}")
    else:
        age = time.time() - HOME_SNAPSHOT_CACHE.get("timestamp", 0)
        if age >= HOME_SNAPSHOT_TTL and not HOME_SNAPSHOT_CACHE.get("refreshing"):
            asyncio.create_task(_refresh_home_snapshot(force=False))

    payload = dict(data or {"heatmap": {"results": []}, "macro": None})
    payload["cacheAgeSec"] = round(max(0.0, time.time() - HOME_SNAPSHOT_CACHE.get("timestamp", 0)), 1)
    payload["refreshing"] = bool(HOME_SNAPSHOT_CACHE.get("refreshing"))
    payload["cacheMode"] = "stale-while-revalidate"
    return payload


@app.get("/api/fwd-per")
@app.get("/api/valuation")
async def valuation_data(tickers: str):
'''
    text = replace_once(text, insert_anchor, snapshot_code, 'home snapshot endpoint')
    MAIN.write_text(text, encoding='utf-8')


def patch_home_js() -> None:
    text = HOME_JS.read_text(encoding='utf-8')

    stocks_old = '''  const HOME_MAJOR_STOCKS = [\n    { symbol: '005930.KS', name: '삼성전자', domain: 'samsung.com' },\n    { symbol: '000660.KS', name: 'SK하이닉스', domain: 'skhynix.com' },\n    { symbol: 'NVDA', name: '엔비디아', domain: 'nvidia.com' },\n    { symbol: 'AAPL', name: '애플', domain: 'apple.com' },\n    { symbol: 'MSFT', name: '마이크로소프트', domain: 'microsoft.com' },\n    { symbol: 'META', name: '메타', domain: 'meta.com' },\n    { symbol: 'TSLA', name: '테슬라', domain: 'tesla.com' },\n    { symbol: 'GOOGL', name: '알파벳', domain: 'google.com' },\n  ];\n'''
    stocks_new = '''  const HOME_MAJOR_STOCKS = [\n    { symbol: '005930.KS', name: '삼성전자', logo: 'https://cdn.simpleicons.org/samsung/1428A0', fallback: '삼성' },\n    { symbol: '000660.KS', name: 'SK하이닉스', logo: null, fallback: 'SK', fallbackColor: '#e8522f' },\n    { symbol: 'NVDA', name: '엔비디아', logo: 'https://cdn.simpleicons.org/nvidia/76B900', fallback: 'NV' },\n    { symbol: 'AAPL', name: '애플', logo: 'https://cdn.simpleicons.org/apple/111111', fallback: 'A' },\n    { symbol: 'MSFT', name: '마이크로소프트', logo: 'https://cdn.simpleicons.org/microsoft/5E5E5E', fallback: 'MS' },\n    { symbol: 'META', name: '메타', logo: 'https://cdn.simpleicons.org/meta/0866FF', fallback: 'M' },\n    { symbol: 'TSLA', name: '테슬라', logo: 'https://cdn.simpleicons.org/tesla/E82127', fallback: 'T' },\n    { symbol: 'GOOGL', name: '알파벳', logo: 'https://cdn.simpleicons.org/google/4285F4', fallback: 'G' },\n  ];\n'''
    text = replace_once(text, stocks_old, stocks_new, 'brand logo map')

    logo_old = '''  function homeLogo(item) {\n    const initials = esc(String(item.name || item.symbol || '?').replace(/[^0-9A-Za-z가-힣]/g, '').slice(0, 2).toUpperCase() || '?');\n    const fallback = `<span class="home16-logo-fallback">${initials}</span>`;\n    if (!item.domain) return `<span class="home16-logo">${fallback}</span>`;\n    const src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(item.domain)}&sz=128`;\n    return `<span class="home16-logo"><img src="${src}" alt="" loading="lazy" decoding="async" onerror="this.style.display='none'">${fallback}</span>`;\n  }\n'''
    logo_new = '''  function homeLogo(item) {\n    const label = esc(item.fallback || String(item.name || item.symbol || '?').slice(0, 2));\n    const color = item.fallbackColor ? ` style="color:${esc(item.fallbackColor)}"` : '';\n    const fallback = `<span class="home16-logo-fallback"${color}>${label}</span>`;\n    if (!item.logo) return `<span class="home16-logo">${fallback}</span>`;\n    return `<span class="home16-logo"><img src="${esc(item.logo)}" alt="" loading="eager" decoding="async" onerror="this.remove()">${fallback}</span>`;\n  }\n'''
    text = replace_once(text, logo_old, logo_new, 'logo renderer')

    checked_old = '''  function homeCheckedAt() {\n    try {\n      return new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })\n        .format(new Date()).replace(/\\. /g, '.').replace(/\\.$/, '');\n    } catch (_) { return '최신'; }\n  }\n'''
    checked_new = '''  function homeCheckedAt(raw) {\n    const match = String(raw || '').match(/^(\\d{4})-(\\d{2})-(\\d{2})[ T](\\d{2}):(\\d{2})/);\n    if (match) return `${match[2]}.${match[3]} ${match[4]}:${match[5]}`;\n    try {\n      return new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })\n        .format(new Date()).replace(/\\. /g, '.').replace(/\\.$/, '');\n    } catch (_) { return '최신'; }\n  }\n'''
    text = replace_once(text, checked_old, checked_new, 'snapshot time formatter')

    header_old = '''  function majorStocksHtml(rows) {\n'''
    header_new = '''  function majorStocksHtml(rows, generatedAt) {\n'''
    text = replace_once(text, header_old, header_new, 'major header signature')
    text = replace_once(text, '''          <small>${esc(homeCheckedAt())} 기준</small>\n''', '''          <small>${esc(homeCheckedAt(generatedAt))} 기준</small>\n''', 'major header time')

    load_old = '''  function loadHomeSources() {\n    if (!homePromise) {\n      homePromise = Promise.all([\n        fetch('/api/heatmap', { cache: 'no-store' }).then((r) => r.ok ? r.json() : { results: [] }).catch(() => ({ results: [] })),\n        fetch('/api/macro', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null).catch(() => null),\n      ]);\n    }\n    return homePromise;\n  }\n'''
    load_new = '''  function loadHomeSources(fresh = false) {\n    const request = () => fetch(`/api/home-snapshot${fresh ? '?fresh=1' : ''}`, { cache: 'no-store' })\n      .then((r) => { if (!r.ok) throw new Error(`home snapshot HTTP ${r.status}`); return r.json(); });\n    if (fresh) return request();\n    if (!homePromise) homePromise = request();\n    return homePromise;\n  }\n\n  function saveHomeLocal(snapshot) {\n    try { localStorage.setItem('chartview-home-snapshot-v17', JSON.stringify(snapshot)); } catch (_) {}\n  }\n\n  function readHomeLocal() {\n    try {\n      const raw = localStorage.getItem('chartview-home-snapshot-v17');\n      return raw ? JSON.parse(raw) : null;\n    } catch (_) { return null; }\n  }\n\n  function paintHome(root, snapshot) {\n    const rows = majorRows(snapshot?.heatmap || { results: [] });\n    root.innerHTML = majorStocksHtml(rows, snapshot?.generatedAt) + moversHtml(rows) + marketSummaryHtml(snapshot?.macro);\n    bindHomeActions(root);\n  }\n'''
    text = replace_once(text, load_old, load_new, 'shared snapshot loader')

    render_old = '''  async function renderHome() {\n    const root = document.getElementById('home-v8-body');\n    if (!root) return;\n    root.innerHTML = '<div class="home-v8-loading"><div class="spinner"></div><span>오늘 시황을 불러오는 중...</span></div>';\n    try {\n      // Refresh live-ish home data every time Home is opened; stock-detail caches stay untouched.\n      homePromise = null;\n      const [heatmap, macro] = await loadHomeSources();\n      const rows = majorRows(heatmap);\n      root.innerHTML = majorStocksHtml(rows) + moversHtml(rows) + marketSummaryHtml(macro);\n      bindHomeActions(root);\n    } catch (error) {\n      console.error('home market dashboard failed', error);\n      root.innerHTML = '<div class="home-v8-empty">오늘 시황을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';\n    }\n  }\n'''
    render_new = '''  async function renderHome() {\n    const root = document.getElementById('home-v8-body');\n    if (!root) return;\n\n    // 1) Same-device cache paints synchronously, so returning users never stare at a spinner.\n    const local = readHomeLocal();\n    if (local?.heatmap?.results?.length) paintHome(root, local);\n    else if (!root.querySelector('.home16-major-card')) {\n      root.innerHTML = '<div class="home-v8-loading"><div class="spinner"></div><span>마지막 시황을 불러오는 중...</span></div>';\n    }\n\n    try {\n      // 2) Shared server cache is returned immediately for every visitor.\n      homePromise = null;\n      const cached = await loadHomeSources(false);\n      if (cached?.heatmap?.results?.length) {\n        paintHome(root, cached);\n        saveHomeLocal(cached);\n      }\n\n      // 3) Latest quotes refresh behind the already-painted UI. Never block Home on this request.\n      loadHomeSources(true).then((fresh) => {\n        if (!fresh?.heatmap?.results?.length) return;\n        saveHomeLocal(fresh);\n        if (document.body.contains(root)) paintHome(root, fresh);\n      }).catch((error) => console.warn('home background refresh failed', error));\n    } catch (error) {\n      console.error('home market dashboard failed', error);\n      if (!root.querySelector('.home16-major-card')) {\n        root.innerHTML = '<div class="home-v8-empty">마지막 시황을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';\n      }\n    }\n  }\n'''
    text = replace_once(text, render_old, render_new, 'stale while revalidate renderer')

    text = text.replace('등락률은 직전 종가 대비 · 종목을 누르면 상세 분석으로 이동', '직전 종가 대비 · 캐시 즉시 표시 후 최신 시세로 자동 갱신')
    HOME_JS.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    patch_main()
    patch_home_js()
    print('HOME V17 cache + logos applied')
