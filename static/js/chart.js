/**
 * 토스 미니앱 - 차트 로직 (개선)
 * 섹터별 선택, 날짜 선택 기능 추가
 * 한국 주식 기업명 표시 + 스마트 검색
 */

let chart = null;
let series = {};
let selectedTickers = ['AAPL', 'NVDA', '005930.KS'];
let currentPeriod = '1mo';
let customDateRange = null;
let chartLoadSeq = 0;
const chartDataCache = new Map();
const chartDataInflight = new Map();
const CHART_CACHE_TTL = 5 * 60 * 1000;
const CHART_PREFETCH_CONCURRENCY = 2;
let chartPrefetchGeneration = 0;
let chartLibraryPromise = null;

function chartCacheKey(period = currentPeriod) {
    const range = customDateRange ? `${customDateRange.start}:${customDateRange.end}` : '';
    return `${selectedTickers.join(',')}|${period}|${range}`;
}

function cachedChartEntry(period = currentPeriod) {
    return chartDataCache.get(chartCacheKey(period)) || null;
}

function isChartCacheFresh(entry) {
    return Boolean(entry?.data && Date.now() - Number(entry.storedAt || 0) < CHART_CACHE_TTL);
}

async function fetchChartData(period = currentPeriod, options = {}) {
    const key = chartCacheKey(period);
    const cached = chartDataCache.get(key);
    if (!options.force && isChartCacheFresh(cached)) return cached.data;
    if (chartDataInflight.has(key)) return chartDataInflight.get(key);

    let url = `/api/compare?tickers=${encodeURIComponent(selectedTickers.join(','))}&period=${period}`;
    if (customDateRange) url += `&start=${customDateRange.start}&end=${customDateRange.end}`;

    // Shared in-flight requests are intentionally not tied to the active UI AbortController.
    // chartLoadSeq decides which response is allowed to paint, so rapid period changes cannot
    // cancel a request that another period switch or background prefetch is already sharing.
    const job = fetch(url, { cache: 'default' }).then(async (res) => {
        if (!res.ok) throw new Error(`차트 API 오류 (${res.status})`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        chartDataCache.set(key, { data, storedAt: Date.now() });
        return data;
    }).finally(() => chartDataInflight.delete(key));
    chartDataInflight.set(key, job);
    return job;
}

async function prefetchChartPeriods() {
    if (customDateRange || !selectedTickers.length) return;
    const generation = ++chartPrefetchGeneration;
    const queue = ['1mo', '3mo', '6mo', 'ytd', '1y']
        .filter((period) => period !== currentPeriod && !isChartCacheFresh(cachedChartEntry(period)));

    const worker = async () => {
        while (queue.length && generation === chartPrefetchGeneration) {
            const period = queue.shift();
            if (!period) return;
            try { await fetchChartData(period); } catch (_) { }
        }
    };
    await Promise.all(Array.from({ length: Math.min(CHART_PREFETCH_CONCURRENCY, queue.length) }, worker));
}

function scheduleChartPrefetch() {
    const run = () => prefetchChartPeriods().catch(() => {});
    if ('requestIdleCallback' in window) window.requestIdleCallback(run, { timeout: 1800 });
    else setTimeout(run, 450);
}

// 티커 → 기업명 매핑 (검색/추가 시 저장)
const tickerNameMap = { '005930.KS': '삼성전자' };

// 토스 색상 팔레트
const COLORS = ['#3182F6', '#00C853', '#FF5252', '#FF9800', '#9C27B0', '#00BCD4'];

// 차트 옵션
const chartOptions = {
    localization: { locale: 'ko-KR' },
    layout: {
        background: { type: 'solid', color: '#FFFFFF' },
        textColor: '#191F28',
        fontFamily: 'Pretendard, sans-serif',
    },
    grid: {
        vertLines: { color: '#E5E8EB' },
        horzLines: { color: '#E5E8EB' },
    },
    crosshair: {
        mode: 0, // LightweightCharts.CrosshairMode.Normal
        vertLine: { color: '#8B95A1', width: 1, style: 2 },
        horzLine: { color: '#8B95A1', width: 1, style: 2 },
    },
    rightPriceScale: { borderColor: '#E5E8EB' },
    timeScale: { borderColor: '#E5E8EB', timeVisible: true },
    handleScroll: { mouseWheel: false, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { mouseWheel: false, pinch: true },
};

// 티커 표시 이름 가져오기
function getDisplayName(ticker) {
    if (tickerNameMap[ticker]) {
        return tickerNameMap[ticker];
    }
    return ticker;
}

// 짧은 표시명 (태그용)
function getShortDisplayName(ticker) {
    const name = tickerNameMap[ticker];
    if (name) {
        // 한국 주식이면 기업명만 표시
        if (ticker.includes('.KS') || ticker.includes('.KQ')) {
            return name;
        }
        return ticker;
    }
    return ticker;
}

function loadLightweightCharts() {
    if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts);
    if (chartLibraryPromise) return chartLibraryPromise;

    chartLibraryPromise = new Promise((resolve, reject) => {
        let script = document.querySelector('script[data-lightweight-charts]');
        if (!script) {
            script = document.createElement('script');
            script.src = 'https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js';
            script.async = true;
            script.dataset.lightweightCharts = '1';
            document.head.appendChild(script);
        }

        const finish = () => {
            if (window.LightweightCharts) resolve(window.LightweightCharts);
            else reject(new Error('Lightweight Charts library unavailable'));
        };
        script.addEventListener('load', finish, { once: true });
        script.addEventListener('error', () => reject(new Error('Lightweight Charts library failed to load')), { once: true });
        if (window.LightweightCharts) finish();
    }).catch((error) => {
        chartLibraryPromise = null;
        throw error;
    });

    return chartLibraryPromise;
}

// 차트 초기화
function initChart() {
    if (chart) return chart;
    const container = document.getElementById('chart-container');
    if (!container || !window.LightweightCharts) return null;

    chart = window.LightweightCharts.createChart(container, {
        ...chartOptions,
        width: Math.max(container.clientWidth, 1),
        height: 260,
    });

    window.addEventListener('resize', () => {
        if (chart && container.clientWidth > 0) chart.resize(container.clientWidth, 260);
    });

    setDefaultDates();
    updateTags();
    return chart;
}

async function ensureChartReady() {
    if (chart) return true;
    try {
        await loadLightweightCharts();
        return !!initChart();
    } catch (error) {
        console.error('Chart library load error:', error);
        chartStatus('차트 모듈을 불러오지 못했습니다. 다시 시도해주세요.');
        return false;
    }
}

async function ensureChartVisible() {
    const chartTab = document.getElementById('chart-tab');
    const container = document.getElementById('chart-container');
    if (!container || !chartTab?.classList.contains('active') || document.body.classList.contains('app-booting')) return false;
    if (!chart && !(await ensureChartReady())) return false;
    const width = container.clientWidth;
    if (width <= 0) return false;
    chart.resize(width, 260);
    if (Object.keys(series).length) {
        chart.timeScale().fitContent();
        return true;
    }
    loadData();
    return true;
}
window.__ensureChartVisible = ensureChartVisible;
window.__ensureChartReady = ensureChartReady;

// 날짜 기본값
function setDefaultDates() {
    const today = new Date();
    const monthAgo = new Date();
    monthAgo.setMonth(today.getMonth() - 1);

    const endInput = document.getElementById('end-date');
    const startInput = document.getElementById('start-date');
    const todayValue = localDate(today);
    if (endInput) {
        endInput.value = todayValue;
        endInput.max = todayValue;
    }
    if (startInput) {
        startInput.value = localDate(monthAgo);
        startInput.max = todayValue;
    }
}

function localDate(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function setCustomDateError(message = '') {
    const node = document.getElementById('custom-date-error');
    const startInput = document.getElementById('start-date');
    const endInput = document.getElementById('end-date');
    const invalid = Boolean(message);
    if (node) {
        node.textContent = message;
        node.hidden = !invalid;
    }
    [startInput, endInput].forEach((input) => {
        if (!input) return;
        input.setAttribute('aria-invalid', invalid ? 'true' : 'false');
    });
}

function clearChartData() {
    Object.values(series).forEach(item => { try { chart.removeSeries(item); } catch (_) {} });
    series = {};
    updateLegend([]);
}

function normalizeChartDate(value) {
    if (value === null || value === undefined || value === '') return null;
    const raw = String(value).trim();
    let date;
    if (typeof value === 'number' || /^\d{10,13}$/.test(raw)) {
        const numeric = Number(raw);
        if (!Number.isFinite(numeric)) return null;
        date = new Date(numeric < 1e12 ? numeric * 1000 : numeric);
    } else {
        date = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(`${raw}T00:00:00Z`) : new Date(raw);
    }
    if (Number.isNaN(date.getTime())) return null;
    return date;
}

function chartTradeDates(data) {
    return (Array.isArray(data?.stocks) ? data.stocks : []).map((stock) => {
        const raw = Array.isArray(stock?.data) && stock.data.length ? stock.data[stock.data.length - 1]?.time : null;
        const date = normalizeChartDate(raw);
        return { ticker: stock?.ticker || '', raw, date, day: date ? date.toISOString().slice(0, 10) : '' };
    }).filter((item) => item.day);
}

function formatKstTime(value) {
    const date = normalizeChartDate(value);
    if (!date) return '';
    try {
        return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
    } catch (_) { return ''; }
}

function updateChartFreshness(data, stale = false) {
    const unit = document.querySelector('#chart-tab .chart-unit');
    if (!unit) return;
    const tradeDates = chartTradeDates(data);
    const uniqueDays = [...new Set(tradeDates.map((item) => item.day))];
    const latestDay = uniqueDays.slice().sort().at(-1) || '';
    const shortTrade = latestDay ? latestDay.slice(5).replace('-', '.') : '';
    const fetchedAt = data?.fetchedAt || data?.timestamp || '';
    const shortFetch = formatKstTime(fetchedAt);
    const mixedDates = uniqueDays.length > 1;
    const parts = [
        stale ? '이전 캐시' : '',
        mixedDates ? '종목별 기준일 상이' : (shortTrade ? `${shortTrade} 거래` : '기준일 미확인'),
        shortFetch ? `${shortFetch} KST 조회` : '',
    ].filter(Boolean);
    unit.textContent = parts.join(' · ');
    unit.dataset.stale = stale ? 'true' : 'false';
    unit.title = [
        '수익률은 기간 시작=0% 기준',
        mixedDates ? tradeDates.map((item) => `${item.ticker || '종목'} ${item.day}`).join(', ') : (latestDay ? `실제 거래일 ${latestDay}` : '실제 거래일 미확인'),
        fetchedAt ? `서버 조회 ${String(fetchedAt)} · 화면 표시는 KST` : '서버 조회 시각 미확인',
    ].filter(Boolean).join(' · ');
}

function chartStatus(message = '') {
    const section = document.querySelector('.chart-section');
    let status = document.getElementById('chart-status');
    if (!status) {
        status = document.createElement('div');
        status.id = 'chart-status';
        status.className = 'ux-data-status';
        status.setAttribute('role', 'status');
        section.appendChild(status);
    }
    status.replaceChildren();
    status.hidden = !message;
    if (!message) return;
    status.append(document.createTextNode(message + ' '));
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'period-chip';
    retry.textContent = '다시 시도';
    retry.addEventListener('click', loadData);
    status.appendChild(retry);
}

// 검색 API로 가장 유사한 종목 찾기
async function searchAndAdd(query) {
    query = query.trim();
    if (!query) return;

    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await res.json();

        if (data.results && data.results.length > 0) {
            // 첫 번째 결과(가장 유사한 종목) 추가
            const best = data.results[0];
            addGlobalTicker(best.symbol, best.name);
        } else if (/^[A-Za-z^][A-Za-z0-9.^=\-]{0,19}$/.test(query)) {
            addGlobalTicker(query.toUpperCase());
        }
    } catch (e) {
        console.error('Search error:', e);
        chartStatus('종목 검색을 완료하지 못했습니다.');
    }
}

// 직접 티커 추가 (검색 없이)
function addTickerDirect(ticker) {
    ticker = ticker.trim().toUpperCase();
    if (!/^[A-Z0-9^][A-Z0-9.^=\-]{0,19}$/.test(ticker)) return;
    if (!ticker || selectedTickers.includes(ticker)) return;

    if (selectedTickers.length >= 6) {
        alert('최대 6개까지 추가할 수 있어요');
        return;
    }

    selectedTickers.push(ticker);
    updateTags();
    loadData();

    // 밸류에이션 탭과 동기화
    if (typeof addPerTickerDirect === 'function' && typeof perTickers !== 'undefined' && !perTickers.includes(ticker)) {
        addPerTickerDirect(ticker);
    }
}

// 티커 추가 (칩 클릭 등에서 사용 - 검색 API 통해 이름 가져오기)
function addTicker(ticker) {
    ticker = ticker.trim();
    if (!ticker) return;

    // 이미 추가된 경우
    if (selectedTickers.includes(ticker)) return;

    // 이름 매핑이 없으면 검색 API로 이름 가져오기
    if (!tickerNameMap[ticker]) {
        fetch(`/api/search?q=${encodeURIComponent(ticker)}`)
            .then(res => res.json())
            .then(data => {
                if (data.results) {
                    const match = data.results.find(r => r.symbol === ticker);
                    if (match) {
                        tickerNameMap[ticker] = match.name;
                        updateTags(); // 이름으로 태그 갱신
                    }
                }
            })
            .catch(() => { });
    }

    addTickerDirect(ticker);
}

// ★ Global Filter: 차트 + 밸류에이션 동시 추가
function addGlobalTicker(ticker, name) {
    ticker = ticker.trim();
    if (!ticker) return;

    // 이름 매핑 저장
    if (name) {
        tickerNameMap[ticker] = name;
        if (typeof perTickerNameMap !== 'undefined') perTickerNameMap[ticker] = name;
    }

    // 1) 차트 측 추가
    addTicker(ticker);

    // 2) 밸류에이션 측 추가 (fwdper.js의 함수 호출)
    if (typeof addPerTickerDirect === 'function') {
        if (typeof perTickers !== 'undefined' && !perTickers.includes(ticker)) {
            addPerTickerDirect(ticker);
        }
    }
    if (typeof window.__focusStockBrief === 'function') window.__focusStockBrief(ticker);
}

// 검색 결과 선택 (Global Filter: 양쪽 동시 반영)
function selectSearchResult(symbol, name) {
    if (name) {
        tickerNameMap[symbol] = name;
        if (typeof perTickerNameMap !== 'undefined') perTickerNameMap[symbol] = name;
    }
    addTickerDirect(symbol);
    // 밸류에이션에도 추가
    if (typeof addPerTickerDirect === 'function' && typeof perTickers !== 'undefined' && !perTickers.includes(symbol)) {
        addPerTickerDirect(symbol);
    }
    if (typeof window.__focusStockBrief === 'function') window.__focusStockBrief(symbol);
    const input = document.getElementById('unified-input');
    if (input) input.value = '';
    document.getElementById('search-results').classList.add('hidden');
}

// 티커 제거 (Global Filter: 양쪽 동시 제거)
function removeTicker(ticker) {
    selectedTickers = selectedTickers.filter(t => t !== ticker);
    if (series[ticker]) {
        try { chart.removeSeries(series[ticker]); } catch (e) { }
        delete series[ticker];
    }
    updateTags();
    loadData();
    // 밸류에이션에서도 제거
    if (typeof removePerTicker === 'function' && typeof perTickers !== 'undefined' && perTickers.includes(ticker)) {
        removePerTicker(ticker);
    }
}

// 태그 업데이트
function updateTags() {
    const container = document.getElementById('ticker-tags');
    container.innerHTML = '';

    selectedTickers.forEach((ticker, i) => {
        const tag = document.createElement('div');
        tag.className = 'ticker-tag';
        const displayName = getShortDisplayName(ticker);
        tag.innerHTML = `<span class="tag-dot" style="background:${COLORS[i % COLORS.length]}"></span><span class="tag-name"></span><button class="tag-remove">×</button>`;
        tag.querySelector('.tag-name').textContent = displayName;
        tag.querySelector('button').setAttribute('aria-label', `${displayName} 제거`);
        tag.querySelector('button').addEventListener('click', () => removeTicker(ticker));
        container.appendChild(tag);
    });
}

// 데이터 로드
async function loadData() {
    const chartTab = document.getElementById('chart-tab');
    if (!chartTab?.classList.contains('active') || document.body.classList.contains('app-booting')) return false;
    const seq = ++chartLoadSeq;
    chartPrefetchGeneration += 1;
    if (!chart && !(await ensureChartReady())) return false;
    const chartSection = document.querySelector('#chart-tab .chart-section');
    chartSection?.setAttribute('aria-busy', 'true');

    if (!selectedTickers.length) {
        clearChartData();
        chartStatus();
        showLoading(false);
        chartSection?.setAttribute('aria-busy', 'false');
        return;
    }

    const period = currentPeriod;
    const key = chartCacheKey(period);
    const staleEntry = chartDataCache.get(key);
    showLoading(true);
    chartStatus();

    const paint = (data, stale = false) => {
        const stocks = Array.isArray(data?.stocks) ? data.stocks : [];
        Object.keys(series).forEach((ticker) => {
            try { chart.removeSeries(series[ticker]); } catch (_) { }
        });
        series = {};

        stocks.forEach((stock) => {
            if (stock.name && !tickerNameMap[stock.ticker]) tickerNameMap[stock.ticker] = stock.name;
            if (!Array.isArray(stock.data) || stock.data.length === 0) return;
            const colorIndex = Math.max(0, selectedTickers.indexOf(stock.ticker));
            const line = chart.addLineSeries({
                color: COLORS[colorIndex % COLORS.length],
                lineWidth: 2,
                priceLineVisible: false,
            });
            line.setData(stock.data);
            series[stock.ticker] = line;
        });

        if (stocks.length) chart.timeScale().fitContent();
        updateTags();
        updateLegend(stocks);
        updateChartFreshness(data, stale);
        return stocks;
    };

    // If an expired entry exists for this exact selection/period, show it immediately
    // while refreshing instead of leaving a different period on screen.
    if (staleEntry?.data && !isChartCacheFresh(staleEntry)) {
        paint(staleEntry.data, true);
    }

    try {
        const data = await fetchChartData(period);
        if (seq !== chartLoadSeq || key !== chartCacheKey(period)) return;
        const stocks = paint(data, false);
        showLoading(false);
        scheduleChartPrefetch();

        if (!stocks.length && selectedTickers.length) {
            chartStatus(customDateRange
                ? '이 기간의 거래 데이터가 없습니다. 기간을 변경해 보세요.'
                : '시세 데이터를 가져오지 못했습니다.');
        } else if (data.errors?.length) {
            chartStatus('일부 종목의 시세를 가져오지 못했습니다.');
        }
    } catch (error) {
        if (seq !== chartLoadSeq) return;
        const hasExistingChart = Object.keys(series).length > 0;
        chartStatus(hasExistingChart
            ? '새 데이터 갱신에 실패했습니다. 표시 중인 차트는 유지했습니다.'
            : '차트 조회에 실패했습니다. 연결을 확인해주세요.');
        console.error('Chart load error:', error);
    } finally {
        if (seq === chartLoadSeq) {
            showLoading(false);
            chartSection?.setAttribute('aria-busy', 'false');
        }
    }
}

// 범례 업데이트
function updateLegend(stocks) {
    const container = document.getElementById('legend');
    container.innerHTML = '';

    stocks.forEach((stock, i) => {
        const isUp = stock.return >= 0;
        const displayName = getDisplayName(stock.ticker);
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `
            <span class="legend-dot" style="background:${COLORS[selectedTickers.indexOf(stock.ticker) % COLORS.length]}"></span>
            <span class="legend-name"></span>
            <span class="legend-value ${isUp ? 'up' : 'down'}">${isUp ? '+' : ''}${stock.return}%</span>
        `;
        item.querySelector('.legend-name').textContent = displayName;
        container.appendChild(item);
    });
}

// 로딩
function showLoading(show) {
    const section = document.querySelector('.chart-section');
    if (!section) return;
    let indicator = section.querySelector('.ux-inline-loader');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.className = 'ux-inline-loader';
        indicator.style.position = 'absolute';
        indicator.style.top = '84px';
        indicator.style.right = '16px';
        indicator.style.zIndex = '8';
        indicator.style.margin = '0';
        indicator.innerHTML = '<span class="ux-mini-spinner"></span><span>차트 업데이트 중</span>';
        const header = section.querySelector('.chart-header');
        if (header) header.insertAdjacentElement('afterend', indicator); else section.prepend(indicator);
    }
    indicator.classList.toggle('show', !!show);
}

// 이벤트 리스너
document.addEventListener('DOMContentLoaded', () => {
    // Keep cheap UI state ready, but defer the chart library and chart instance
    // until the user actually enters analysis.
    setDefaultDates();
    updateTags();

    const chartTab = document.getElementById('chart-tab');
    if (chartTab) {
        new MutationObserver(() => {
            if (chartTab.classList.contains('active')) requestAnimationFrame(() => ensureChartVisible());
        }).observe(chartTab, { attributes: true, attributeFilter: ['class'] });
    }
    document.addEventListener('click', (event) => {
        if (event.target.closest('.tab-btn[data-tab="chart"]')) {
            setTimeout(ensureChartVisible, 0);
        }
    });

    const dateSection = document.querySelector('#chart-tab .date-section');
    const customDateToggle = document.getElementById('custom-date-toggle');
    const customDateFields = document.getElementById('custom-date-fields');

    function setCustomDateOpen(open) {
        if (!customDateToggle || !customDateFields) return;
        const rangeContainer = customDateToggle.closest('.v40-chart-periods') || dateSection;
        if (!rangeContainer) return;
        rangeContainer.classList.toggle('custom-range-open', open);
        customDateToggle.setAttribute('aria-expanded', String(open));
        customDateFields.hidden = !open;
        const arrow = customDateToggle.querySelector('.custom-date-arrow');
        if (arrow) arrow.textContent = open ? '⌃' : '⌄';
    }

    if (customDateToggle) {
        customDateToggle.addEventListener('click', () => {
            setCustomDateOpen(customDateToggle.getAttribute('aria-expanded') !== 'true');
        });
    }

    // 기간 선택 칩
    document.querySelectorAll('.period-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            setCustomDateOpen(false);
            document.querySelectorAll('.period-chip').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentPeriod = btn.dataset.period;

            if (currentPeriod === 'ytd') {
                // YTD: 올해 1월 1일 ~ 오늘
                const today = new Date();
                const yearStart = new Date(today.getFullYear(), 0, 1);
                customDateRange = {
                    start: localDate(yearStart),
                    end: localDate(today)
                };
                document.getElementById('start-date').value = customDateRange.start;
                document.getElementById('end-date').value = customDateRange.end;
                currentPeriod = '1y'; // fallback period
            } else {
                customDateRange = null;
            }
            loadData();
        });
    });

    // 추가 버튼 - 스마트 검색 적용
    document.getElementById('add-btn').addEventListener('click', () => {
        const input = document.getElementById('unified-input');
        searchAndAdd(input.value);
        input.value = '';
        document.getElementById('search-results').classList.add('hidden');
    });

    // 통합 입력창 - 엔터 키와 검색 기능
    const unifiedInput = document.getElementById('unified-input');
    const searchResults = document.getElementById('search-results');
    let searchTimeout = null;

    if (unifiedInput) {
        // 엔터 키 - 스마트 검색 적용
        unifiedInput.addEventListener('keypress', e => {
            if (e.key === 'Enter') {
                searchAndAdd(e.target.value);
                e.target.value = '';
                searchResults.classList.add('hidden');
            }
        });

        // 입력 시 검색 자동완성
        unifiedInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            const query = unifiedInput.value.trim();

            if (query.length < 1) {
                searchResults.classList.add('hidden');
                return;
            }

            searchTimeout = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                    const data = await res.json();
                    if (unifiedInput.value.trim() !== query) return;
                    searchResults.replaceChildren();
                    const rows = Array.isArray(data.results) ? data.results : [];
                    rows.forEach(r => {
                        const item = document.createElement('div');
                        item.className = 'search-result-item';
                        const name = document.createElement('span');
                        name.className = 'name'; name.textContent = r.name;
                        const symbol = document.createElement('span');
                        symbol.className = 'symbol'; symbol.textContent = r.market ? `${r.code || r.symbol} · ${r.market}` : r.symbol;
                        item.append(name, symbol);
                        item.addEventListener('click', () => selectSearchResult(r.symbol, r.name));
                        searchResults.appendChild(item);
                    });
                    searchResults.classList.toggle('hidden', !rows.length);
                } catch (e) {
                    console.error('Search error:', e);
                }
            }, 300);
        });

        // 검색창 외부 클릭 시 닫기
        document.addEventListener('click', (e) => {
            if (!unifiedInput.contains(e.target) && !searchResults.contains(e.target)) {
                searchResults.classList.add('hidden');
            }
        });
    }

    // 날짜 적용 버튼
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    [startDateInput, endDateInput].forEach((input) => input?.addEventListener('input', () => setCustomDateError('')));
    document.getElementById('apply-date-btn').addEventListener('click', () => {
        const start = startDateInput?.value || '';
        const end = endDateInput?.value || '';
        const today = localDate(new Date());

        if (!start || !end) {
            setCustomDateError('시작일과 종료일을 모두 선택해 주세요.');
            return;
        }
        if (start > end) {
            setCustomDateError('시작일은 종료일보다 빠르거나 같아야 합니다.');
            return;
        }
        if (start > today || end > today) {
            setCustomDateError('미래 날짜는 조회할 수 없습니다. 오늘 이전 날짜를 선택해 주세요.');
            return;
        }

        setCustomDateError('');
        customDateRange = { start, end };
        document.querySelectorAll('.period-chip').forEach(b => b.classList.remove('active'));
        loadData();
    });
});
