/**
 * 밸류에이션 비교 로직 (정밀화 버전)
 * PER, PBR, PSR, EV/EBITDA 등 모든 지표 대응
 */

let perData = [];
let currentSort = 'default';
let currentMetric = 'overview';
let perTickers = ['AAPL', 'NVDA'];

// 티커 -> 기업명 매핑
const perTickerNameMap = {};

// 지표 메타 정보 (탭의 모든 데이터 속성과 일치시킴)
const METRIC_CONFIG = {
    'overview': {
        title: '종합 밸류에이션 비교',
        description: '주요 투자 지표를 한눈에 비교합니다.',
        columns: [
            { key: 'forwardPE', label: 'FWD PER', format: 'number', color: true },
            { key: 'pbr', label: 'PBR', format: 'number', color: true },
            { key: 'psr', label: 'PSR', format: 'number', color: true },
            { key: 'dividendYield', label: '배당률(%)', format: 'percent', color: true }
        ],
        barKey: 'forwardPE',
        barLabel: 'FWD PER (선행)',
        sortKey: 'forwardPE',
        colorFunc: (v) => v > 0 && v < 25 ? '#3182F6' : '#6B7684'
    },
    'fwd_per': {
        title: 'Forward PER (선행)',
        description: '향후 12개월 예상 이익 대비 주가 수준입니다.',
        columns: [
            { key: 'forwardPE', label: 'FWD PER', format: 'number', color: true },
            { key: 'forwardEPS', label: 'FWD EPS($)', format: 'currency' },
            { key: 'trailingPE', label: 'PER(실적)', format: 'number' }
        ],
        sortKey: 'forwardPE',
        barKey: 'forwardPE',
        barLabel: 'FWD PER (선행)',
        colorFunc: (v) => v < 20 ? '#00C853' : (v < 40 ? '#3182F6' : '#F44336')
    },
    'trailing_pe': {
        title: 'Trailing PER (실적)',
        description: '최근 12개월 발표된 실제 이익 대비 주가 수준입니다.',
        columns: [
            { key: 'trailingPE', label: 'PER(실적)', format: 'number', color: true },
            { key: 'trailingEPS', label: '현재 EPS($)', format: 'currency' },
            { key: 'forwardPE', label: 'FWD PER', format: 'number' }
        ],
        sortKey: 'trailingPE',
        barKey: 'trailingPE',
        barLabel: 'PER (실적)',
        colorFunc: (v) => v < 20 ? '#00C853' : (v < 40 ? '#3182F6' : '#F44336')
    },
    'pbr': {
        title: 'PBR (주가순자산비율)',
        description: '기업의 순자산 가치 대비 주가 수준입니다. 1보다 낮으면 저평가로 봅니다.',
        columns: [
            { key: 'pbr', label: 'PBR', format: 'number', color: true },
            { key: 'bookValue', label: 'BPS(장부가액)', format: 'currency' },
            { key: 'roe', label: 'ROE(%)', format: 'percent' }
        ],
        sortKey: 'pbr',
        barKey: 'pbr',
        barLabel: 'PBR (주가순자산비율)',
        colorFunc: (v) => v < 1.0 ? '#00C853' : (v < 3.0 ? '#3182F6' : '#F44336')
    },
    'psr': {
        title: 'PSR (주가매출비율)',
        description: '기업의 매출 대비 주가 수준입니다. 성장주 평가에 주로 쓰입니다.',
        columns: [
            { key: 'psr', label: 'PSR', format: 'number', color: true },
            { key: 'marketCap', label: '시가총액', format: 'marketcap' }
        ],
        sortKey: 'psr',
        barKey: 'psr',
        barLabel: 'PSR (주가매출비율)',
        colorFunc: (v) => v < 2.0 ? '#00C853' : (v < 8.0 ? '#3182F6' : '#F44336')
    },
    'ev': {
        title: 'EV/EBITDA',
        description: '기업이 영업활동으로 버는 돈 대비 기업 가치가 몇 배인지 나타냅니다.',
        columns: [
            { key: 'evEbitda', label: 'EV/EBITDA', format: 'number', color: true },
            { key: 'operatingMargin', label: '영업이익률(%)', format: 'percent' }
        ],
        sortKey: 'evEbitda',
        barKey: 'evEbitda',
        barLabel: 'EV/EBITDA',
        colorFunc: (v) => v < 10 ? '#00C853' : (v < 20 ? '#3182F6' : '#F44336')
    },
    'dividend': {
        title: '배당수익률',
        description: '현재 주가 대비 연간 배당금의 비율입니다.',
        columns: [
            { key: 'dividendYield', label: '배당수익률(%)', format: 'percent', color: true },
            { key: 'price', label: '현재가', format: 'currency' }
        ],
        sortKey: 'dividendYield',
        barKey: 'dividendYield',
        barLabel: '배당수익률(%)',
        colorFunc: (v) => v > 3.0 ? '#00C853' : (v > 1.0 ? '#3182F6' : '#6B7684')
    },
    'profitability': {
        title: '수익성 (ROE)',
        description: '자기자본 대비 얼마나 이익을 냈는지 보여주는 지표입니다.',
        columns: [
            { key: 'roe', label: 'ROE(%)', format: 'percent', color: true },
            { key: 'operatingMargin', label: '영업이익률(%)', format: 'percent' }
        ],
        sortKey: 'roe',
        barKey: 'roe',
        barLabel: 'ROE (자기자본이익률)',
        colorFunc: (v) => v > 15 ? '#00C853' : (v > 8 ? '#3182F6' : '#F44336')
    }
};

function getPerDisplayName(ticker) {
    return perTickerNameMap[ticker] || ticker;
}

function updatePerTags() {
    const container = document.getElementById('ticker-tags');
    if (!container) return;
    // index.html의 Global Filter 영역과 동기화
    if (typeof updateTags === 'function') updateTags();
}

async function loadPerData() {
    if (perTickers.length === 0) {
        const container = document.getElementById('per-table-container');
        if (container) container.innerHTML = '<div class="per-empty">종목을 선택하면 밸류에이션 비교 결과가 표시됩니다</div>';
        return;
    }

    const loading = document.getElementById('per-loading') || document.getElementById('loading');
    if (loading) loading.classList.remove('hidden');

    try {
        const res = await fetch(`/api/valuation?tickers=${perTickers.join(',')}`);
        const data = await res.json();
        if (data.stocks) {
            perData = data.stocks;
            perData.forEach(s => { if (s.name && !perTickerNameMap[s.ticker]) perTickerNameMap[s.ticker] = s.name; });
            renderPerTable();
        }
    } catch (e) {
        console.error('PER data error:', e);
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}

function formatValue(val, format, isKR) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    if (format === 'currency') return isKR ? `₩${Math.round(val).toLocaleString()}` : `$${val.toLocaleString()}`;
    if (format === 'percent') return `${val.toFixed(2)}%`;
    if (format === 'marketcap') {
        if (isKR) return `${(val / 100000000).toFixed(0)}억`;
        return `$${(val / 1000000000).toFixed(1)}B`;
    }
    return val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

function renderPerTable() {
    const container = document.getElementById('per-table-container');
    const titleEl = document.getElementById('metric-title');
    const descEl = document.getElementById('metric-description');

    if (!container) return;

    const config = METRIC_CONFIG[currentMetric] || METRIC_CONFIG['overview'];

    if (titleEl) titleEl.textContent = config.title;
    if (descEl) descEl.textContent = config.description;

    if (perData.length === 0) {
        container.innerHTML = '<div class="per-empty">데이터를 불러오는 중...</div>';
        return;
    }

    // 1. 정렬 로직 적용
    let sortedData = [...perData];
    const sortField = config.sortKey;

    if (currentSort === 'metric-asc' && sortField) {
        sortedData.sort((a, b) => (a[sortField] ?? -999999) - (b[sortField] ?? -999999));
    } else if (currentSort === 'metric-desc' && sortField) {
        sortedData.sort((a, b) => (b[sortField] ?? -999999) - (a[sortField] ?? -999999));
    }

    let html = `<table class="per-table"><thead><tr><th>종목</th><th>현재가</th>`;
    config.columns.forEach(col => { html += `<th>${col.label}</th>`; });
    html += `</tr></thead><tbody>`;

    sortedData.forEach(stock => {
        const isKR = stock.ticker.includes('.KS') || stock.ticker.includes('.KQ');
        const priceStr = isKR ? `₩${stock.price?.toLocaleString()}` : `$${stock.price?.toLocaleString()}`;
        html += `<tr>
            <td class="stock-info-cell">
                <div class="stock-name">${perTickerNameMap[stock.ticker] || stock.name || stock.ticker}</div>
                <div class="stock-ticker">${stock.ticker}</div>
            </td>
            <td class="price-cell">${priceStr}</td>`;

        config.columns.forEach(col => {
            const val = stock[col.key];
            const color = col.color ? config.colorFunc(val) : 'inherit';
            html += `<td style="color:${color}; font-weight: ${col.color ? '600' : 'normal'}">${formatValue(val, col.format, isKR)}</td>`;
        });
        html += `</tr>`;
    });
    html += '</tbody></table>';

    // 바 차트 (시각 비교)
    const barKey = config.barKey;
    if (barKey && sortedData.length > 0) {
        const validData = sortedData.filter(s => s[barKey] != null && !isNaN(s[barKey]) && s[barKey] !== 0);
        if (validData.length > 0) {
            const vals = validData.map(s => Math.abs(s[barKey]));
            const maxVal = Math.max(...vals, 0.1);

            html += `<div class="per-bars">
                <div class="per-bars-title">${config.barLabel || config.title} 한눈에 보기</div>`;

            validData.forEach(stock => {
                const val = stock[barKey];
                const width = Math.min((Math.abs(val) / maxVal) * 100, 100);
                const color = config.colorFunc ? config.colorFunc(val) : '#3182F6';
                const label = getPerDisplayName(stock.ticker);

                html += `
                    <div class="per-bar-row">
                        <span class="per-bar-label">${label}</span>
                        <div class="per-bar-track">
                            <div class="per-bar-fill" style="width:${width}%; background:${color}"></div>
                        </div>
                        <span class="per-bar-value" style="color:${color}">${(val || 0).toFixed(1)}</span>
                    </div>`;
            });
            html += '</div>';
        }
    }

    container.innerHTML = html;
}

// Global Filter 상호작용 지점
window.addPerTickerDirect = function (ticker) {
    if (!perTickers.includes(ticker)) {
        perTickers.push(ticker);
        loadPerData();
        // 차트와 동기화
        if (typeof addTickerDirect === 'function' && typeof selectedTickers !== 'undefined' && !selectedTickers.includes(ticker)) {
            addTickerDirect(ticker);
        }
    }
};

window.removePerTicker = function (ticker) {
    perTickers = perTickers.filter(t => t !== ticker);
    perData = perData.filter(d => d.ticker !== ticker);
    renderPerTable();
    // 차트와 동기화
    if (typeof removeTicker === 'function' && typeof selectedTickers !== 'undefined' && selectedTickers.includes(ticker)) {
        removeTicker(ticker);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // 탭 전환 로직 (통신 필요 시 loadPerData 호출)
    window.switchTab = function (tabId) {
        console.log('Switching to tab:', tabId);

        // 버튼 활성화 상태 변경
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });

        // 콘텐츠 표시/숨김
        document.querySelectorAll('.tab-content').forEach(content => {
            if (content.id === `${tabId}-tab`) {
                content.classList.add('active');
                content.style.display = 'block';
            } else {
                content.classList.remove('active');
                content.style.display = 'none';
            }
        });

        // 글로벌 필터(상단 바) 노출 여부 조절
        const globalFilter = document.getElementById('global-filter');
        if (globalFilter) {
            globalFilter.style.display = (tabId === 'chart' || tabId === 'fwdper') ? 'block' : 'none';
        }

        // 탭 전용 데이터 로드
        if (tabId === 'fwdper') {
            loadPerData();
        } else if (tabId === 'macro' && typeof loadMacroData === 'function') {
            loadMacroData();
        }
    };

    // 하단 탭 버튼들 이벤트 연결 (누락되었던 부분)
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // 지표 칩 클릭 이벤트
    document.querySelectorAll('.metric-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.metric-chip').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentMetric = btn.dataset.metric;
            renderPerTable();
        });
    });

    // 정렬 버튼 이벤트
    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSort = btn.dataset.sort;
            renderPerTable();
        });
    });

    // 초기 로드
    loadPerData();
});