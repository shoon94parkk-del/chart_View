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
let chartRequestController = null;
let chartLoadSeq = 0;

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
        mode: LightweightCharts.CrosshairMode.Normal,
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

// 차트 초기화
function initChart() {
    const container = document.getElementById('chart-container');

    chart = LightweightCharts.createChart(container, {
        ...chartOptions,
        width: container.clientWidth,
        height: 260,
    });

    window.addEventListener('resize', () => {
        chart.resize(container.clientWidth, 260);
    });

    // 날짜 기본값 설정
    setDefaultDates();

    updateTags();
    loadData();
}

// 날짜 기본값
function setDefaultDates() {
    const today = new Date();
    const monthAgo = new Date();
    monthAgo.setMonth(today.getMonth() - 1);

    document.getElementById('end-date').value = localDate(today);
    document.getElementById('start-date').value = localDate(monthAgo);
}

function localDate(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function clearChartData() {
    Object.values(series).forEach(item => { try { chart.removeSeries(item); } catch (_) {} });
    series = {};
    updateLegend([]);
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
    const seq = ++chartLoadSeq;
    if (chartRequestController) chartRequestController.abort();
    chartRequestController = new AbortController();

    if (!selectedTickers.length) {
        clearChartData();
        chartStatus();
        showLoading(false);
        return;
    }

    showLoading(true);
    chartStatus();

    try {
        let url = `/api/compare?tickers=${encodeURIComponent(selectedTickers.join(','))}&period=${currentPeriod}`;
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
                color: COLORS[selectedTickers.indexOf(stock.ticker) % COLORS.length],
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
            chartStatus('시세 데이터를 가져오지 못했습니다.');
        } else if (data.errors?.length) {
            chartStatus('일부 종목의 시세를 가져오지 못했습니다.');
        }
    } catch (e) {
        if (e && e.name === 'AbortError') return;
        if (seq !== chartLoadSeq) return;
        clearChartData();
        chartStatus('차트 조회에 실패했습니다. 연결을 확인해주세요.');
        console.error('Chart load error:', e);
    } finally {
        // An older aborted request must not hide the loader for a newer request.
        if (seq === chartLoadSeq) showLoading(false);
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
        indicator.innerHTML = '<span class="ux-mini-spinner"></span><span>차트 업데이트 중</span>';
        const header = section.querySelector('.chart-header');
        if (header) header.insertAdjacentElement('afterend', indicator); else section.prepend(indicator);
    }
    indicator.classList.toggle('show', !!show);
}

// 이벤트 리스너
document.addEventListener('DOMContentLoaded', () => {
    initChart();

    const dateSection = document.querySelector('#chart-tab .date-section');
    const customDateToggle = document.getElementById('custom-date-toggle');
    const customDateFields = document.getElementById('custom-date-fields');

    function setCustomDateOpen(open) {
        if (!dateSection || !customDateToggle || !customDateFields) return;
        dateSection.classList.toggle('custom-range-open', open);
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
    document.getElementById('apply-date-btn').addEventListener('click', () => {
        const start = document.getElementById('start-date').value;
        const end = document.getElementById('end-date').value;

        if (start && end) {
            if (start > end) {
                alert('시작일은 종료일보다 늦을 수 없어요');
                return;
            }
            customDateRange = { start, end };
            document.querySelectorAll('.period-chip').forEach(b => b.classList.remove('active'));
            loadData();
        }
    });
});
