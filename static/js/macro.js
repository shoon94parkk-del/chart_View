/**
 * 경제 지표 (Macro Insight) 로직
 * 순유동성 차트 + 한줄 요약 포함
 */

// fwdper.js에서 switchTab을 통해 통합 관리
document.addEventListener('DOMContentLoaded', () => {
    // 탭 클릭 시에만 로드
});

async function loadMacroData() {
    const grid = document.getElementById('macro-grid');
    if (!grid) return;

    grid.innerHTML = '<div class="macro-loading-inner"><div class="spinner"></div><p>글로벌 경제 데이터를 번역하고 있습니다...</p></div>';

    // 요약 영역 초기화
    const summaryEl = document.getElementById('macro-summary');
    if (summaryEl) summaryEl.innerHTML = '';

    try {
        const res = await fetch('/api/macro');
        const data = await res.json();

        if (data.results && data.results.length > 0) {
            // 1. 한줄 요약 렌더링
            if (data.summary) {
                renderMacroSummary(data.summary);
            }

            // 2. 순유동성 차트 렌더링 (일반 카드 위에)
            if (data.net_liquidity && !data.net_liquidity.error) {
                renderNetLiquidityCard(data.net_liquidity);
            }

            // 3. 개별 지표 카드 렌더링
            renderMacroGrid(data.results);
        } else {
            grid.innerHTML = '<div class="macro-error">데이터를 불러오지 못했습니다.</div>';
        }
    } catch (e) {
        console.error('Macro load error:', e);
        grid.innerHTML = '<div class="macro-error">서버 연결에 실패했습니다.</div>';
    }
}

function renderMacroSummary(summary) {
    // summary는 {text: "...", level: "red|yellow|green"} 객체
    const text = typeof summary === 'string' ? summary : summary.text;
    const level = typeof summary === 'string' ? 'green' : (summary.level || 'green');

    // 신호등 색상 매핑
    const lightConfig = {
        red: { color: '#F04452', bg: 'linear-gradient(135deg, #FFF0F0, #FFE8E8)', border: '#FFD0D0', label: '위험' },
        yellow: { color: '#FF9800', bg: 'linear-gradient(135deg, #FFF8E1, #FFF3CD)', border: '#FFE0A0', label: '주의' },
        green: { color: '#00C853', bg: 'linear-gradient(135deg, #E8F5E9, #F0FFF0)', border: '#C8E6C9', label: '안정' }
    };
    const cfg = lightConfig[level] || lightConfig.green;

    let summaryEl = document.getElementById('macro-summary');
    if (!summaryEl) {
        const section = document.querySelector('.macro-section');
        if (!section) return;
        summaryEl = document.createElement('div');
        summaryEl.id = 'macro-summary';
        const header = section.querySelector('.macro-header');
        if (header && header.nextSibling) {
            section.insertBefore(summaryEl, header.nextSibling);
        } else {
            section.appendChild(summaryEl);
        }
    }

    summaryEl.className = 'macro-summary-box';
    summaryEl.style.background = cfg.bg;
    summaryEl.style.borderColor = cfg.border;

    summaryEl.innerHTML = `
        <div class="traffic-light">
            <span class="tl-dot ${level === 'red' ? 'active' : ''}" style="--dot-color: #F04452;"></span>
            <span class="tl-dot ${level === 'yellow' ? 'active' : ''}" style="--dot-color: #FF9800;"></span>
            <span class="tl-dot ${level === 'green' ? 'active' : ''}" style="--dot-color: #00C853;"></span>
        </div>
        <div class="summary-content">
            <span class="summary-label" style="color: ${cfg.color};">${cfg.label}</span>
            <span class="summary-text">${text}</span>
        </div>
    `;
}

function renderNetLiquidityCard(nlData) {
    const grid = document.getElementById('macro-grid');
    if (!grid) return;

    // 순유동성 전용 카드를 grid 맨 위에 추가
    const card = document.createElement('div');
    card.className = 'macro-card net-liquidity-card';
    card.style.gridColumn = '1 / -1';  // 풀와이드

    const isUp = nlData.change > 0;
    const colorClass = isUp ? 'up' : 'down';
    const sign = isUp ? '+' : '';
    const chartId = 'macro-chart-net-liquidity';

    // 값 포맷: 백만달러 → 조 달러
    const trillionVal = (nlData.value / 1000000).toFixed(2);

    card.innerHTML = `
        <div class="mc-header">
            <span class="mc-name">${nlData.name} <span class="nl-badge">CORE</span></span>
            <span class="mc-symbol">WALCL - TGA - RRP</span>
        </div>
        <div class="mc-value-row">
            <span class="mc-value">$${trillionVal}T</span>
            <span class="mc-change ${colorClass}">${sign}${nlData.change}%</span>
        </div>
        <div class="mc-chart-wrapper" style="height: 120px;">
            <div id="${chartId}" class="mc-mini-chart" style="height: 120px;"></div>
            <div class="mc-chart-dates">
                <span>${nlData.chart_data[0]?.time || ''}</span>
                <span>${nlData.chart_data[nlData.chart_data.length - 1]?.time || ''}</span>
            </div>
        </div>
        <div class="mc-desc">${nlData.desc}</div>
    `;

    // grid 맨 앞에 삽입
    grid.insertBefore(card, grid.firstChild);

    // 차트 그리기
    setTimeout(() => {
        const chartContainer = document.getElementById(chartId);
        if (!chartContainer) return;

        const chart = LightweightCharts.createChart(chartContainer, {
            width: chartContainer.clientWidth,
            height: 120,
            layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#999' },
            grid: { vertLines: { visible: false }, horzLines: { visible: false } },
            rightPriceScale: { visible: false },
            timeScale: { visible: false, borderVisible: false },
            handleScroll: false,
            handleScale: false,
        });

        const areaColor = isUp ? 'rgba(0, 200, 83, 0.1)' : 'rgba(240, 68, 82, 0.1)';
        const lineColor = isUp ? '#00C853' : '#F04452';

        const areaSeries = chart.addAreaSeries({
            topColor: areaColor,
            bottomColor: 'transparent',
            lineColor: lineColor,
            lineWidth: 2,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
        });

        areaSeries.setData(nlData.chart_data);
        chart.timeScale().fitContent();

        window.addEventListener('resize', () => {
            if (chartContainer.clientWidth > 0) {
                chart.resize(chartContainer.clientWidth, 120);
                chart.timeScale().fitContent();
            }
        });
    }, 100);
}

function renderMacroGrid(indicators) {
    const grid = document.getElementById('macro-grid');
    // 순유동성 카드가 이미 들어있을 수 있으므로 기존 일반 카드만 제거
    const existingCards = grid.querySelectorAll('.macro-card:not(.net-liquidity-card)');
    existingCards.forEach(c => c.remove());

    // 로딩 메시지 제거
    const loadingInner = grid.querySelector('.macro-loading-inner');
    if (loadingInner) loadingInner.remove();

    indicators.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'macro-card';
        card.style.cursor = 'pointer';

        card.addEventListener('click', () => {
            if (item.link) window.open(item.link, '_blank');
        });

        const isError = item.error === true;
        const isUp = !isError && item.change > 0;
        const colorClass = isError ? 'neutral' : (isUp ? 'up' : 'down');
        const sign = isUp ? '+' : '';
        const chartId = `macro-chart-${index}`;

        const valueDisplay = isError ? 'N/A' : item.value.toLocaleString();
        const changeDisplay = isError ? '-' : `${sign}${item.change}%`;

        // 날짜 정보
        const hasChart = !isError && item.chart_data && item.chart_data.length > 0;
        const startDate = hasChart ? item.chart_data[0].time : '';
        const endDate = hasChart ? item.chart_data[item.chart_data.length - 1].time : '';

        card.innerHTML = `
            <div class="mc-header">
                <span class="mc-name">${item.name} <span class="link-icon">&#x2197;</span></span>
                <span class="mc-symbol">${item.symbol}</span>
            </div>
            <div class="mc-value-row">
                <span class="mc-value">${valueDisplay}</span>
                <span class="mc-change ${colorClass}">${changeDisplay}</span>
            </div>
            <div class="mc-chart-wrapper">
                <div id="${chartId}" class="mc-mini-chart">
                    ${!hasChart ? '<div class="no-chart">데이터 수집 실패</div>' : ''}
                </div>
                ${hasChart ? `
                <div class="mc-chart-dates">
                    <span>${startDate}</span>
                    <span>${endDate}</span>
                </div>` : ''}
            </div>
            <div class="mc-desc">${item.desc}</div>
        `;

        grid.appendChild(card);

        // 미니 차트 생성
        if (hasChart) {
            setTimeout(() => {
                const chartContainer = document.getElementById(chartId);
                if (!chartContainer) return;

                const chart = LightweightCharts.createChart(chartContainer, {
                    width: chartContainer.clientWidth,
                    height: 80,
                    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#999' },
                    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
                    rightPriceScale: { visible: false },
                    timeScale: { visible: false, borderVisible: false },
                    handleScroll: false,
                    handleScale: false,
                });

                let lineColor = isUp ? '#F04452' : '#3182F6';
                if (item.symbol === '^VIX' || item.symbol === 'T10YIE') {
                    lineColor = item.value > 20 || item.change > 0 ? '#F04452' : '#3182F6';
                }

                const lineSeries = chart.addLineSeries({
                    color: lineColor,
                    lineWidth: 2,
                    priceLineVisible: false,
                    crosshairMarkerVisible: false,
                });

                lineSeries.setData(item.chart_data);
                chart.timeScale().fitContent();

                window.addEventListener('resize', () => {
                    if (chartContainer.clientWidth > 0) {
                        chart.resize(chartContainer.clientWidth, 80);
                        chart.timeScale().fitContent();
                    }
                });
            }, 50);
        }
    });
}
