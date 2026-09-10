from pathlib import Path
import re

# ---------- market_service.py ----------
p = Path('market_service.py')
text = p.read_text(encoding='utf-8')

cache_marker = '# disk-valuation-detail-cache-v3'
if cache_marker not in text:
    anchor = '_auth_state: dict[str, Any] = {"cookies": None, "crumb": None, "timestamp": 0.0}\n'
    if anchor not in text:
        raise SystemExit('market auth state anchor missing')
    insert = '''

# disk-valuation-detail-cache-v3
_detail_cache_lock = threading.Lock()
_detail_cache: dict[str, dict[str, Any]] | None = None


def _local_detail_cache() -> dict[str, dict[str, Any]]:
    """Read the daily GitHub-generated quote cache once per process."""
    global _detail_cache
    if _detail_cache is not None:
        return _detail_cache
    with _detail_cache_lock:
        if _detail_cache is not None:
            return _detail_cache
        rows: dict[str, dict[str, Any]] = {}
        try:
            path = os.path.join(os.path.dirname(__file__), "static", "data", "valuation_cache.json")
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            raw_rows = payload.get("quotes") or {}
            if isinstance(raw_rows, dict):
                rows = {str(k).upper(): v for k, v in raw_rows.items() if isinstance(v, dict)}
        except Exception as exc:
            print(f"[MarketData] valuation detail cache unavailable: {exc}")
        _detail_cache = rows
        return rows


def _cached_quote_summary(symbol: str) -> dict[str, Any] | None:
    """Adapt a flat daily quote row to the subset of quoteSummary used below."""
    row = _local_detail_cache().get(symbol.upper())
    if not row:
        return None

    def rv(value: Any) -> dict[str, Any]:
        return {"raw": value} if value is not None else {}

    dividend = _number(row.get("dividendYield"))
    # v7/quote exposes dividendYield in percentage units (e.g. 0.34 == 0.34%).
    dividend_fraction = dividend / 100 if dividend is not None else None
    return {
        "price": {
            "shortName": row.get("shortName"),
            "currency": row.get("currency"),
            "regularMarketPrice": rv(row.get("regularMarketPrice")),
            "marketCap": rv(row.get("marketCap")),
        },
        "summaryDetail": {
            "marketCap": rv(row.get("marketCap")),
            "trailingPE": rv(row.get("trailingPE")),
            "forwardPE": rv(row.get("forwardPE")),
            "dividendYield": rv(dividend_fraction),
        },
        "defaultKeyStatistics": {
            "trailingEps": rv(row.get("epsTrailingTwelveMonths")),
            "forwardEps": rv(row.get("epsForward")),
            "forwardPE": rv(row.get("forwardPE")),
            "priceToBook": rv(row.get("priceToBook")),
            "bookValue": rv(row.get("bookValue")),
        },
        "financialData": {},
        "assetProfile": {},
    }
'''
    text = text.replace(anchor, anchor + insert, 1)

old_auth = '''        if not force and _auth_state.get("crumb") and now - float(_auth_state.get("timestamp") or 0) < 1800:
            return dict(_auth_state["cookies"]), str(_auth_state["crumb"])'''
new_auth = '''        auth_age = now - float(_auth_state.get("timestamp") or 0)
        if not force and _auth_state.get("timestamp") and auth_age < 1800:
            # Cache failures too. Render shared IPs can be rate-limited by Yahoo; without
            # negative caching concurrent tickers each retried the same slow crumb call.
            if _auth_state.get("crumb") and _auth_state.get("cookies"):
                return dict(_auth_state["cookies"]), str(_auth_state["crumb"])
            return None'''
if old_auth in text:
    text = text.replace(old_auth, new_auth, 1)
elif 'Cache failures too.' not in text:
    raise SystemExit('auth cache anchor missing')

old_detail = '    detail = _quote_summary(symbol) or {}\n'
new_detail = '    cached_detail = _cached_quote_summary(symbol)\n    detail = cached_detail or _quote_summary(symbol) or {}\n'
if old_detail in text:
    text = text.replace(old_detail, new_detail, 1)
elif 'cached_detail = _cached_quote_summary(symbol)' not in text:
    raise SystemExit('detail anchor missing')

old_source = '        "dataSource": "Yahoo Chart + Fundamentals" + (" + QuoteSummary" if detail else "") + (" + Naver" if naver else ""),\n'
new_source = '        "dataSource": "Yahoo Chart + Fundamentals" + (" + Daily Quote Cache" if cached_detail else (" + QuoteSummary" if detail else "")) + (" + Naver" if naver else ""),\n'
if old_source in text:
    text = text.replace(old_source, new_source, 1)
elif 'Daily Quote Cache' not in text:
    raise SystemExit('source anchor missing')

p.write_text(text, encoding='utf-8')

# ---------- static/js/chart.js ----------
p = Path('static/js/chart.js')
chart = p.read_text(encoding='utf-8-sig')
if 'let chartRequestController = null;' not in chart:
    anchor = 'let customDateRange = null;\n'
    if anchor not in chart:
        raise SystemExit('chart state anchor missing')
    chart = chart.replace(anchor, anchor + 'let chartRequestController = null;\nlet chartLoadSeq = 0;\n', 1)

load_start = chart.index('async function loadData() {')
load_end = chart.index('// 범례 업데이트', load_start)
new_load = '''async function loadData() {
    const seq = ++chartLoadSeq;
    if (chartRequestController) chartRequestController.abort();
    chartRequestController = new AbortController();

    if (!selectedTickers.length) {
        updateLegend([]);
        showLoading(false);
        return;
    }

    showLoading(true);

    try {
        let url = `/api/compare?tickers=${selectedTickers.join(',')}&period=${currentPeriod}&_t=${Date.now()}`;
        if (customDateRange) {
            url += `&start=${customDateRange.start}&end=${customDateRange.end}`;
        }

        const res = await fetch(url, { cache: 'no-store', signal: chartRequestController.signal });
        if (!res.ok) throw new Error(`차트 API 오류 (${res.status})`);
        const data = await res.json();
        if (seq !== chartLoadSeq) return;
        if (data.error) throw new Error(data.error);

        const stocks = Array.isArray(data.stocks) ? data.stocks : [];
        Object.keys(series).forEach(t => {
            try { chart.removeSeries(series[t]); } catch (e) { }
        });
        series = {};

        stocks.forEach((stock, i) => {
            if (stock.name && !tickerNameMap[stock.ticker]) tickerNameMap[stock.ticker] = stock.name;
            if (!Array.isArray(stock.data) || stock.data.length === 0) return;
            const s = chart.addLineSeries({
                color: COLORS[i % COLORS.length],
                lineWidth: 2,
                priceLineVisible: false,
            });
            s.setData(stock.data);
            series[stock.ticker] = s;
        });

        if (stocks.length) chart.timeScale().fitContent();
        updateTags();
        updateLegend(stocks);

        if (!stocks.length && selectedTickers.length) {
            console.warn('No chart data returned', data.errors || []);
        }
    } catch (e) {
        if (e && e.name === 'AbortError') return;
        console.error('Chart load error:', e);
    } finally {
        // An older aborted request must not hide the loader for a newer request.
        if (seq === chartLoadSeq) showLoading(false);
    }
}

'''
chart = chart[:load_start] + new_load + chart[load_end:]

old_date = '''        if (start && end) {
            customDateRange = { start, end };'''
new_date = '''        if (start && end) {
            if (start > end) {
                alert('시작일은 종료일보다 늦을 수 없어요');
                return;
            }
            customDateRange = { start, end };'''
if old_date in chart:
    chart = chart.replace(old_date, new_date, 1)

p.write_text(chart, encoding='utf-8')

# ---------- static/js/fwdper.js ----------
p = Path('static/js/fwdper.js')
js = p.read_text(encoding='utf-8-sig')
if 'let perRequestController = null;' not in js:
    anchor = 'const perTickerNameMap = {};\n'
    if anchor not in js:
        raise SystemExit('valuation state anchor missing')
    js = js.replace(anchor, anchor + 'let perRequestController = null;\nlet perLoadSeq = 0;\n', 1)

js = js.replace("{ key: 'forwardEPS', label: 'FWD EPS($)', format: 'currency' }", "{ key: 'forwardEPS', label: 'FWD EPS', format: 'currency' }")
js = js.replace("{ key: 'trailingEPS', label: '현재 EPS($)', format: 'currency' }", "{ key: 'trailingEPS', label: 'EPS(실적)', format: 'currency' }")

per_start = js.index('async function loadPerData() {')
per_end = js.index('function formatValue', per_start)
new_per = '''async function loadPerData() {
    const seq = ++perLoadSeq;
    if (perRequestController) perRequestController.abort();
    perRequestController = new AbortController();

    const container = document.getElementById('per-table-container');
    if (perTickers.length === 0) {
        perData = [];
        if (container) container.innerHTML = '<div class="per-empty">종목을 선택하면 밸류에이션 비교 결과가 표시됩니다</div>';
        return;
    }

    const loading = document.getElementById('per-loading');
    if (loading) loading.classList.remove('hidden');

    try {
        const res = await fetch(`/api/valuation?tickers=${encodeURIComponent(perTickers.join(','))}`, {
            cache: 'no-store',
            signal: perRequestController.signal,
        });
        if (!res.ok) throw new Error(`밸류에이션 API 오류 (${res.status})`);
        const data = await res.json();
        if (seq !== perLoadSeq) return;

        perData = Array.isArray(data.stocks) ? data.stocks : [];
        perData.forEach(s => {
            if (s.name && !perTickerNameMap[s.ticker]) perTickerNameMap[s.ticker] = s.name;
        });
        renderPerTable();

        const badge = document.getElementById('update-badge');
        if (badge) {
            const failed = Array.isArray(data.errors) ? data.errors.length : 0;
            badge.textContent = failed ? `${failed}개 종목 일부 데이터 누락` : '업데이트 완료';
            badge.classList.remove('hidden');
        }
    } catch (e) {
        if (e && e.name === 'AbortError') return;
        console.error('Valuation data error:', e);
        if (seq === perLoadSeq && container) {
            container.innerHTML = '<div class="per-empty">밸류에이션 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</div>';
        }
    } finally {
        if (seq === perLoadSeq && loading) loading.classList.add('hidden');
    }
}

'''
js = js[:per_start] + new_per + js[per_end:]

old_sort = '''    if (currentSort === 'metric-asc' && sortField) {
        sortedData.sort((a, b) => (a[sortField] ?? -999999) - (b[sortField] ?? -999999));
    } else if (currentSort === 'metric-desc' && sortField) {
        sortedData.sort((a, b) => (b[sortField] ?? -999999) - (a[sortField] ?? -999999));
    }'''
new_sort = '''    if ((currentSort === 'metric-asc' || currentSort === 'metric-desc') && sortField) {
        const direction = currentSort === 'metric-asc' ? 1 : -1;
        sortedData.sort((a, b) => {
            const av = Number(a[sortField]);
            const bv = Number(b[sortField]);
            const aValid = Number.isFinite(av) && a[sortField] !== null;
            const bValid = Number.isFinite(bv) && b[sortField] !== null;
            if (!aValid && !bValid) return 0;
            if (!aValid) return 1;
            if (!bValid) return -1;
            return (av - bv) * direction;
        });
    }'''
if old_sort in js:
    js = js.replace(old_sort, new_sort, 1)
elif 'const direction = currentSort' not in js:
    raise SystemExit('valuation sort anchor missing')

rem_start = js.index('window.removePerTicker = function (ticker) {')
rem_end = js.index('document.addEventListener', rem_start)
new_remove = '''window.removePerTicker = function (ticker) {
    perTickers = perTickers.filter(t => t !== ticker);
    perData = perData.filter(d => d.ticker !== ticker);
    // removeTicker() in chart.js is the single owner of global removal.
    // Calling it again here caused chart -> valuation -> chart recursion.
    const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab;
    if (activeTab === 'fwdper') renderPerTable();
};

'''
js = js[:rem_start] + new_remove + js[rem_end:]
p.write_text(js, encoding='utf-8')

# ---------- templates/index.html ----------
p = Path('templates/index.html')
html = p.read_text(encoding='utf-8')
html = re.sub(r'/static/css/ux_patch\.css\?v=[^"\']+', '/static/css/ux_patch.css?v=20260910v3', html)
html = re.sub(r'/static/js/chart\.js\?v=[^"\']+', '/static/js/chart.js?v=20260910v3', html)
html = re.sub(r'/static/js/fwdper\.js\?v=[^"\']+', '/static/js/fwdper.js?v=20260910v3', html)
html = html.replace('Yahoo Finance 애널리스트 컨센서스 기준', 'Yahoo Finance 공개 시세·재무 데이터 기준 · 없는 값은 - 표시')
p.write_text(html, encoding='utf-8')

# ---------- workflow comment accuracy ----------
p = Path('.github/workflows/update-valuation-cache.yml')
wf = p.read_text(encoding='utf-8')
wf = wf.replace('# 07:30 KST on Korean weekdays, after the US regular session has closed.', '# 07:30 KST Tue-Sat, after each US Mon-Fri regular session has closed.')
p.write_text(wf, encoding='utf-8')

compile(Path('market_service.py').read_text(encoding='utf-8'), 'market_service.py', 'exec')
print('hardening patch complete')
