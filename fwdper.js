/**
 * 밸류에이션 비교 로직
 * PER, PBR, PSR, EV/EBITDA, 배당률, 수익성 지표 선택
 */

let perTickers = [];
let perData = [];
let currentSort = 'default';
let currentMetric = 'fwd_per';

// 티커 → 기업명 매핑
const perTickerNameMap = {};

// 지표 메타 정보
const METRIC_CONFIG = {
    fwd_per: {
        title: 'Forward PER (전망) 비교',
        description: '내년 예상 이익 대비 주가 수준입니다. 낮을수록 앞으로의 성장에 비해 저렴하다는 의미입니다.',
        columns: [
            { key: 'forwardPE', label: 'FWD PER', color: true },
            { key: 'trailingPE', label: 'PER(실적)' },
            { key: 'forwardEPS', label: 'FWD EPS(예)', format: 'currency' },
        ],
        sortKey: 'forwardPE',
        barKey: 'forwardPE',
        barLabel: 'FWD PER (전망)',
        gradeFunc: (v) => {
            if (!v) return '';
            if (v < 10) return '매우 저평가';
            if (v < 15) return '저평가';
            if (v < 20) return '적정';
            if (v < 25) return '약간 고평가';
            if (v < 35) return '고평가';
            return '매우 고평가';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 10) return '#00C853';
            if (v < 15) return '#4CAF50';
            if (v < 20) return '#8BC34A';
            if (v < 25) return '#FF9800';
            if (v < 35) return '#FF5722';
            return '#F44336';
        }
    },
    trailing_pe: {
        title: 'PER (과거 실적 기준) 비교',
        description: '지난 1년 수익 대비 주가 수준입니다. 현재 기업의 실제 돈 버는 능력에 비해 주가가 어떤지 보여줍니다.',
        columns: [
            { key: 'trailingPE', label: 'Trailing PER', color: true },
            { key: 'forwardPE', label: 'FWD PER(전망)' },
            { key: 'trailingEPS', label: 'EPS(실적)', format: 'currency' },
        ],
        sortKey: 'trailingPE',
        barKey: 'trailingPE',
        barLabel: 'Trailing PER (실적)',
        gradeFunc: (v) => {
            if (!v) return '';
            if (v < 10) return '매우 저평가';
            if (v < 15) return '저평가';
            if (v < 20) return '적정';
            if (v < 25) return '약간 고평가';
            if (v < 35) return '고평가';
            return '매우 고평가';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 10) return '#00C853';
            if (v < 15) return '#4CAF50';
            if (v < 20) return '#8BC34A';
            if (v < 25) return '#FF9800';
            if (v < 35) return '#FF5722';
            return '#F44336';
        }
    },
    pbr: {
        title: 'PBR (주가순자산비율) 비교',
        description: '기업의 장부가치(자산) 대비 주가 수준입니다. 1보다 낮으면 회사 자산보다 주가가 싸다는 의미입니다.',
        columns: [
            { key: 'pbr', label: 'PBR', color: true },
            { key: 'bookValue', label: '장부가치', format: 'currency' },
            { key: 'roe', label: 'ROE', format: 'percent' },
        ],
        sortKey: 'pbr',
        barKey: 'pbr',
        barLabel: 'PBR',
        gradeFunc: (v) => {
            if (!v) return '';
            if (v < 1) return '자산 대비 저평가';
            if (v < 2) return '적정';
            if (v < 5) return '성장 프리미엄';
            if (v < 10) return '고평가';
            return '매우 고평가';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 1) return '#00C853';
            if (v < 2) return '#4CAF50';
            if (v < 5) return '#8BC34A';
            if (v < 10) return '#FF9800';
            return '#F44336';
        }
    },
    psr: {
        title: 'PSR (주가매출비율) 비교',
        description: '매출액 대비 주가 수준입니다. 이익이 아직 나지 않는 성장주의 가치를 평가할 때 유용합니다.',
        columns: [
            { key: 'psr', label: 'PSR', color: true },
            { key: 'operatingMargin', label: '영업이익률', format: 'percent' },
        ],
        sortKey: 'psr',
        barKey: 'psr',
        barLabel: 'PSR',
        gradeFunc: (v) => {
            if (!v) return '';
            if (v < 1) return '매우 저평가';
            if (v < 3) return '저평가';
            if (v < 8) return '적정';
            if (v < 15) return '고평가';
            return '매우 고평가';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 1) return '#00C853';
            if (v < 3) return '#4CAF50';
            if (v < 8) return '#8BC34A';
            if (v < 15) return '#FF9800';
            return '#F44336';
        }
    },
    ev: {
        title: 'EV/EBITDA 비교',
        description: '기업이 영업으로 벌어들이는 현금 흐름 대비 기업 가치입니다. 실질적인 현금 창출 능력을 보여줍니다.',
        columns: [
            { key: 'evEbitda', label: 'EV/EBITDA', color: true },
            { key: 'operatingMargin', label: '영업이익률', format: 'percent' },
        ],
        sortKey: 'evEbitda',
        barKey: 'evEbitda',
        barLabel: 'EV/EBITDA',
        gradeFunc: (v) => {
            if (!v) return '';
            if (v < 8) return '저평가';
            if (v < 15) return '적정';
            if (v < 25) return '고평가';
            return '매우 고평가';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 8) return '#00C853';
            if (v < 15) return '#8BC34A';
            if (v < 25) return '#FF9800';
            return '#F44336';
        }
    },
    dividend: {
        title: '배당수익률 비교',
        description: '주가 대비 연간 예상 배당금의 비율입니다. 높을수록 투자금 대비 받는 배당금이 많음을 의미합니다.',
        columns: [
            { key: 'dividendYield', label: '배당률(%)', color: true, reverse: true },
            { key: 'trailingPE', label: 'Trailing PER' },
        ],
        sortKey: 'dividendYield',
        barKey: 'dividendYield',
        barLabel: '배당률(%)',
        gradeFunc: (v) => {
            if (!v) return '무배당';
            if (v < 1) return '낮음';
            if (v < 2.5) return '보통';
            if (v < 5) return '양호';
            return '고배당';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 1) return '#FF9800';
            if (v < 2.5) return '#8BC34A';
            if (v < 5) return '#4CAF50';
            return '#00C853';
        }
    },
    profitability: {
        title: '수익성(ROE) 비교',
        description: '자기자본 대비 얼마나 이익을 냈는지 보여주는 지표입니다. 높을수록 자본을 효율적으로 쓴다는 뜻입니다.',
        columns: [
            { key: 'roe', label: 'ROE(%)', color: true, reverse: true },
            { key: 'operatingMargin', label: '영업이익률(%)' },
            { key: 'forwardPE', label: 'FWD PER' },
        ],
        sortKey: 'roe',
        barKey: 'roe',
        barLabel: 'ROE(%)',
        gradeFunc: (v) => {
            if (!v) return '';
            if (v < 5) return '낮음';
            if (v < 15) return '보통';
            if (v < 25) return '우수';
            return '매우 우수';
        },
        colorFunc: (v) => {
            if (!v) return '#8B95A1';
            if (v < 5) return '#FF5722';
            if (v < 15) return '#FF9800';
            if (v < 25) return '#4CAF50';
            return '#00C853';
        }
    }
};

// 스마트 검색
async function searchAndAddPer(query) {
    query = query.trim();
    if (!query) return;
    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (data.results && data.results.length > 0) {
            const best = data.results[0];
            perTickerNameMap[best.symbol] = best.name;
            addPerTickerDirect(best.symbol);
        } else {
            addPerTickerDirect(query.toUpperCase());
        }
    } catch (e) {
        addPerTickerDirect(query.toUpperCase());
    }
}

function addPerTickerDirect(ticker) {
    ticker = ticker.trim();
    if (!ticker || perTickers.includes(ticker)) return;
    if (perTickers.length >= 20) {
        alert('최대 20개까지 추가할 수 있어요');
        return;
    }
    perTickers.push(ticker);
    updatePerTags();
    loadPerData();
}

function addPerTicker(ticker) {
    ticker = ticker.trim();
    if (!ticker || perTickers.includes(ticker)) return;
    if (!perTickerNameMap[ticker]) {
        fetch(`/api/search?q=${encodeURIComponent(ticker)}`)
            .then(res => res.json())
            .then(data => {
                if (data.results) {
                    const match = data.results.find(r => r.symbol === ticker);
                    if (match) {
                        perTickerNameMap[ticker] = match.name;
                        updatePerTags();
                    }
                }
            }).catch(() => { });
    }
    addPerTickerDirect(ticker);
}

function selectPerSearchResult(symbol, name) {
    if (name) perTickerNameMap[symbol] = name;
    addPerTickerDirect(symbol);
    const input = document.getElementById('per-input');
    if (input) input.value = '';
    document.getElementById('per-search-results').classList.add('hidden');
}

function getPerDisplayName(ticker) {
    if (perTickerNameMap[ticker] && (ticker.includes('.KS') || ticker.includes('.KQ'))) {
        return perTickerNameMap[ticker];
    }
    return ticker;
}

function removePerTicker(ticker) {
    perTickers = perTickers.filter(t => t !== ticker);
    perData = perData.filter(d => d.ticker !== ticker);
    updatePerTags();
    renderPerTable();
}

function updatePerTags() {
    const container = document.getElementById('per-tags');
    if (!container) return;
    container.innerHTML = '';
    const COLORS = ['#3182F6', '#00C853', '#FF5252', '#FF9800', '#9C27B0', '#00BCD4'];
    perTickers.forEach((ticker, i) => {
        const tag = document.createElement('div');
        tag.className = 'ticker-tag';
        const data = perData.find(d => d.ticker === ticker);
        let label;
        if (ticker.includes('.KS') || ticker.includes('.KQ')) {
            label = (data && data.name) || perTickerNameMap[ticker] || ticker;
        } else {
            label = ticker;
        }
        tag.innerHTML = `
            <span class="tag-dot" style="background:${COLORS[i % COLORS.length]}"></span>
            <span class="tag-name">${label}</span>
            <button class="tag-remove" onclick="removePerTicker('${ticker}')">×</button>
        `;
        container.appendChild(tag);
    });
}

// 데이터 로드
async function loadPerData() {
    if (perTickers.length === 0) {
        const container = document.getElementById('per-table-container');
        if (container) container.innerHTML = '<div class="per-empty">종목을 선택하면 밸류에이션 비교 결과가 표시됩니다</div>';
        return;
    }
    const loading = document.getElementById('per-loading');
    if (loading) loading.classList.remove('hidden');
    try {
        const res = await fetch(`/api/valuation?tickers=${perTickers.join(',')}`);
        const data = await res.json();
        if (data.stocks) {
            perData = data.stocks;
            console.log('Valuation data loaded:', perData);
            perData.forEach(s => { if (s.name) perTickerNameMap[s.ticker] = s.name; });

            // 업데이트 시간 표시
            const badge = document.getElementById('update-badge');
            if (badge && data.timestamp) {
                badge.textContent = `최근 업데이트: ${data.timestamp}`;
                badge.classList.remove('hidden');
            }

            updatePerTags();
            renderPerTable();
        } else {
            throw new Error('No stock data received');
        }
    } catch (e) {
        console.error('PER data error:', e);
        const container = document.getElementById('per-table-container');
        if (container) container.innerHTML =
            '<div class="per-empty">데이터 수집 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. (Yahoo Finance 서버 지연 가능성)</div>';
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}

function formatValue(val, format, isKR) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    if (format === 'currency') {
        try {
            return isKR ? `₩${Math.round(val).toLocaleString()}` : `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        } catch (e) {
            return val;
        }
    }
    if (format === 'percent') {
        return `${val.toFixed(1)}%`;
    }
    return val.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function renderPerTable() {
    const container = document.getElementById('per-table-container');
    if (!container) return;

    const config = METRIC_CONFIG[currentMetric];
    if (!config) {
        console.error('Invalid metric selection:', currentMetric);
        return;
    }

    if (perData.length === 0 && perTickers.length > 0) {
        container.innerHTML = '<div class="per-empty">데이터를 불러오는 중...</div>';
        return;
    } else if (perData.length === 0) {
        container.innerHTML = '<div class="per-empty">종목을 선택하면 밸류에이션 비교 결과가 표시됩니다</div>';
        return;
    }

    // 타이틀 및 설명 업데이트
    const titleEl = document.getElementById('metric-title');
    if (titleEl) titleEl.textContent = config.title;

    const descEl = document.getElementById('metric-description');
    if (descEl) descEl.textContent = config.description || '';

    // 정렬
    let sorted = [...perData];
    const sKey = config.sortKey;
    if (currentSort === 'metric-asc') {
        sorted.sort((a, b) => {
            const va = a[sKey] === null || a[sKey] === undefined ? Infinity : a[sKey];
            const vb = b[sKey] === null || b[sKey] === undefined ? Infinity : b[sKey];
            return va - vb;
        });
    } else if (currentSort === 'metric-desc') {
        sorted.sort((a, b) => {
            const va = a[sKey] === null || a[sKey] === undefined ? -Infinity : a[sKey];
            const vb = b[sKey] === null || b[sKey] === undefined ? -Infinity : b[sKey];
            return vb - va;
        });
    }

    // 테이블 헤더
    let html = `<table class="per-table"><thead><tr>
        <th class="th-name">종목</th>
        <th class="th-price">현재가</th>`;
    config.columns.forEach(col => {
        html += `<th class="th-per">${col.label}</th>`;
    });
    html += `</tr></thead><tbody>`;

    // 테이블 로우
    sorted.forEach(stock => {
        const isKR = stock.ticker.includes('.KS') || stock.ticker.includes('.KQ');
        const priceStr = isKR ? `₩${stock.price?.toLocaleString() || '-'}` : `$${stock.price?.toLocaleString(undefined, { minimumFractionDigits: 2 }) || '-'}`;

        html += `<tr><td class="td-name">
            <div class="stock-name">${stock.name || stock.ticker}</div>
            <div class="stock-ticker">${stock.ticker}</div>
        </td><td class="td-price">${priceStr}</td>`;

        config.columns.forEach((col, ci) => {
            const val = stock[col.key];
            if (ci === 0 && col.color) {
                // 메인 지표 - 색상 + 등급
                const color = config.colorFunc(val);
                const grade = config.gradeFunc(val);
                html += `<td class="td-per">
                    <span class="per-value" style="color:${color}">${val != null && !isNaN(val) ? val.toFixed(1) : '-'}</span>
                    <span class="per-grade" style="color:${color}">${grade}</span>
                </td>`;
            } else if (col.color) {
                const color = config.colorFunc(val);
                html += `<td class="td-per">
                    <span class="per-value" style="color:${color}">${val != null && !isNaN(val) ? val.toFixed(1) : '-'}</span>
                </td>`;
            } else {
                html += `<td class="td-eps">${formatValue(val, col.format, isKR)}</td>`;
            }
        });
        html += `</tr>`;
    });
    html += '</tbody></table>';

    // 바 차트
    const barData = sorted.filter(s => s[config.barKey] != null && !isNaN(s[config.barKey]) && s[config.barKey] > 0);
    if (barData.length > 0) {
        const maxVal = Math.max(...barData.map(s => s[config.barKey]), 0.1);
        html += `<div class="per-bars"><div class="per-bars-title">${config.barLabel} 시각 비교</div>`;
        barData.forEach(stock => {
            const val = stock[config.barKey];
            const width = Math.min((val / maxVal) * 100, 100);
            const color = config.colorFunc(val);
            const label = getPerDisplayName(stock.ticker);
            html += `<div class="per-bar-row">
                <span class="per-bar-label">${label}</span>
                <div class="per-bar-track">
                    <div class="per-bar-fill" style="width:${width}%; background:${color}"></div>
                </div>
                <span class="per-bar-value" style="color:${color}">${val.toFixed(1)}</span>
            </div>`;
        });
        html += '</div>';
    }

    container.innerHTML = html;
}

// 이벤트 리스너
document.addEventListener('DOMContentLoaded', () => {
    // 탭 버튼
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const targetTab = document.getElementById(btn.dataset.tab + '-tab');
            if (targetTab) targetTab.classList.add('active');
        });
    });

    // 지표 선택 칩
    document.querySelectorAll('.metric-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.metric-chip').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentMetric = btn.dataset.metric;
            console.log('Metric changed to:', currentMetric);
            renderPerTable();
        });
    });

    // PER 추가 버튼
    document.getElementById('per-add-btn').addEventListener('click', () => {
        const input = document.getElementById('per-input');
        searchAndAddPer(input.value);
        input.value = '';
        document.getElementById('per-search-results').classList.add('hidden');
    });

    // PER 엔터 키
    const perInput = document.getElementById('per-input');
    const perSearchResults = document.getElementById('per-search-results');

    perInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') {
            searchAndAddPer(e.target.value);
            e.target.value = '';
            perSearchResults.classList.add('hidden');
        }
    });

    // PER 검색
    let perSearchTimeout = null;
    perInput.addEventListener('input', () => {
        clearTimeout(perSearchTimeout);
        const query = perInput.value.trim();
        if (query.length < 1) { perSearchResults.classList.add('hidden'); return; }
        perSearchTimeout = setTimeout(async () => {
            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const data = await res.json();
                if (data.results && data.results.length > 0) {
                    perSearchResults.innerHTML = data.results.map(r => `
                        <div class="search-result-item" onclick="selectPerSearchResult('${r.symbol}', '${r.name.replace(/'/g, "\\'")}')">
                            <span class="name">${r.name}</span>
                            <span class="symbol">${r.symbol}</span>
                        </div>
                    `).join('');
                    perSearchResults.classList.remove('hidden');
                } else {
                    perSearchResults.innerHTML = `
                        <div class="search-result-item" onclick="selectPerSearchResult('${query.toUpperCase()}')">
                            <span class="name">티커로 직접 추가</span>
                            <span class="symbol">${query.toUpperCase()}</span>
                        </div>
                    `;
                    perSearchResults.classList.remove('hidden');
                }
            } catch (e) { console.error('Search error:', e); }
        }, 300);
    });

    // 검색 외부 클릭
    document.addEventListener('click', (e) => {
        if (!perInput.contains(e.target) && !perSearchResults.contains(e.target)) {
            perSearchResults.classList.add('hidden');
        }
    });

    // 정렬 버튼
    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSort = btn.dataset.sort;
            renderPerTable();
        });
    });
});
