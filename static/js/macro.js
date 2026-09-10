/**
 * 경제 지표 (Macro Insight)
 * - Render에서는 사전 생성된 캐시만 읽음
 * - 금리/스프레드는 변화율보다 bp 변화로 표시
 * - 캐시 생성시각/관측 기준일/출처를 화면에 노출
 * - 탭 재진입 시 이전 차트 인스턴스를 정리해 메모리 누수 방지
 */

let macroCharts = [];
let macroObservers = [];
let macroLoadSeq = 0;

const MACRO_RATE_SYMBOLS = new Set(['T10Y2Y', 'T10Y3M', 'BAMLH0A0HYM2', 'DFII10', 'T10YIE', 'FEDFUNDS', 'UNRATE']);

function cleanupMacroCharts() {
    macroObservers.forEach(observer => {
        try { observer.disconnect(); } catch (_) { }
    });
    macroObservers = [];
    macroCharts.forEach(chart => {
        try { chart.remove(); } catch (_) { }
    });
    macroCharts = [];
}

function macroNumber(value, digits = 2) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    return n.toLocaleString('ko-KR', { maximumFractionDigits: digits });
}

function formatMacroValue(item) {
    const symbol = item.original_symbol || item.symbol;
    const value = Number(item.value);
    if (!Number.isFinite(value)) return 'N/A';

    if (MACRO_RATE_SYMBOLS.has(symbol)) return `${macroNumber(value, 2)}%`;
    if (symbol === '^VIX') return macroNumber(value, 2);
    if (symbol === 'RRPONTSYD') return `$${macroNumber(value, 2)}B`;
    if (symbol === 'WALCL' || symbol === 'WTREGEN') return `$${macroNumber(value / 1_000_000, 2)}T`;
    if (symbol === 'M2SL') return `$${macroNumber(value / 1_000, 2)}T`;
    if (symbol === 'RSAFS') return `$${macroNumber(value / 1_000, 1)}B`;
    return macroNumber(value, 2);
}

function formatMacroChange(item) {
    const symbol = item.original_symbol || item.symbol;
    const delta = Number(item.delta);
    const change = Number(item.change);

    if (MACRO_RATE_SYMBOLS.has(symbol) && Number.isFinite(delta)) {
        const bp = delta * 100;
        return `${bp > 0 ? '+' : ''}${bp.toFixed(Math.abs(bp) < 1 ? 1 : 0)}bp`;
    }
    if (symbol === '^VIX' && Number.isFinite(delta)) {
        return `${delta > 0 ? '+' : ''}${delta.toFixed(2)}pt`;
    }
    if (Number.isFinite(change)) return `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
    return '-';
}

function formatGeneratedAt(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).slice(0, 16);
    return d.toLocaleString('ko-KR', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
    });
}

function bindResponsiveChart(container, chart, height) {
    macroCharts.push(chart);
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(entries => {
        const width = Math.floor(entries[0]?.contentRect?.width || 0);
        if (width > 0) chart.resize(width, height);
    });
    observer.observe(container);
    macroObservers.push(observer);
}

async function loadMacroData() {
    const seq = ++macroLoadSeq;
    const grid = document.getElementById('macro-grid');
    if (!grid) return;

    cleanupMacroCharts();
    grid.innerHTML = '<div class="macro-loading-inner"><div class="spinner"></div><p>최신 경제지표 캐시를 불러오는 중...</p></div>';

    const summaryEl = document.getElementById('macro-summary');
    if (summaryEl) summaryEl.remove();
    const freshnessEl = document.getElementById('macro-freshness');
    if (freshnessEl) freshnessEl.remove();

    try {
        const res = await fetch('/api/macro', { cache: 'no-store' });
        if (!res.ok) throw new Error(`macro HTTP ${res.status}`);
        const data = await res.json();
        if (seq !== macroLoadSeq) return;

        if (!Array.isArray(data.results) || data.results.length === 0) {
            grid.innerHTML = '<div class="macro-error">경제지표 캐시가 비어 있습니다.</div>';
            return;
        }

        renderMacroFreshness(data);
        if (data.summary) renderMacroSummary(data.summary);
        if (data.net_liquidity && !data.net_liquidity.error) renderNetLiquidityCard(data.net_liquidity);
        renderMacroGrid(data.results);
    } catch (e) {
        console.error('Macro load error:', e);
        if (seq === macroLoadSeq) grid.innerHTML = '<div class="macro-error">경제지표를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
    }
}

function renderMacroFreshness(data) {
    const section = document.querySelector('.macro-section');
    const header = section?.querySelector('.macro-header');
    if (!section || !header) return;

    const stale = Number(data.staleCount || 0);
    const fresh = Number(data.freshCount || 0);
    const box = document.createElement('div');
    box.id = 'macro-freshness';
    box.className = `macro-freshness ${stale ? 'has-stale' : ''}`;
    box.innerHTML = `
        <span class="macro-fresh-main">${stale ? '일부 지표 직전값 유지' : '13개 지표 정상 갱신'}</span>
        <span>캐시 ${formatGeneratedAt(data.generatedAt)}</span>
        <span>fresh ${fresh} · stale ${stale}</span>
    `;
    header.insertAdjacentElement('afterend', box);
}

function renderMacroSummary(summary) {
    const text = typeof summary === 'string' ? summary : summary.text;
    const level = typeof summary === 'string' ? 'green' : (summary.level || 'green');
    const config = {
        red: { label: '위험', className: 'red' },
        yellow: { label: '주의', className: 'yellow' },
        green: { label: '안정', className: 'green' },
    }[level] || { label: '확인', className: 'yellow' };

    const section = document.querySelector('.macro-section');
    const freshness = document.getElementById('macro-freshness');
    if (!section) return;

    const box = document.createElement('div');
    box.id = 'macro-summary';
    box.className = `macro-summary-box macro-summary-${config.className}`;
    box.innerHTML = `
        <div class="traffic-light" aria-hidden="true">
            <span class="tl-dot ${level === 'red' ? 'active' : ''}" style="--dot-color:#F04452"></span>
            <span class="tl-dot ${level === 'yellow' ? 'active' : ''}" style="--dot-color:#FF9800"></span>
            <span class="tl-dot ${level === 'green' ? 'active' : ''}" style="--dot-color:#00C853"></span>
        </div>
        <div class="summary-content">
            <span class="summary-label">시장 환경 · ${config.label}</span>
            <span class="summary-text">${text || '요약 데이터가 없습니다.'}</span>
        </div>`;
    if (freshness) freshness.insertAdjacentElement('afterend', box);
    else section.querySelector('.macro-header')?.insertAdjacentElement('afterend', box);
}

function renderNetLiquidityCard(nlData) {
    const grid = document.getElementById('macro-grid');
    if (!grid) return;

    const card = document.createElement('div');
    card.className = 'macro-card net-liquidity-card';
    card.style.gridColumn = '1 / -1';

    const isUp = Number(nlData.change) >= 0;
    const chartId = 'macro-chart-net-liquidity';
    const trillionVal = Number.isFinite(Number(nlData.value)) ? (Number(nlData.value) / 1_000_000).toFixed(2) : '-';
    const asOf = nlData.chart_data?.at(-1)?.time || '-';

    card.innerHTML = `
        <div class="mc-header">
            <span class="mc-name">${nlData.name} <span class="nl-badge">CORE</span></span>
            <span class="mc-symbol">WALCL - TGA - RRP</span>
        </div>
        <div class="mc-value-row">
            <span class="mc-value">$${trillionVal}T</span>
            <span class="mc-change ${isUp ? 'up' : 'down'}">${Number(nlData.change) > 0 ? '+' : ''}${macroNumber(nlData.change, 2)}%</span>
        </div>
        <div class="mc-chart-wrapper">
            <div id="${chartId}" class="mc-mini-chart mc-mini-chart-core"></div>
            <div class="mc-chart-dates"><span>${nlData.chart_data?.[0]?.time || ''}</span><span>${asOf}</span></div>
        </div>
        <div class="mc-desc">${nlData.desc}</div>
        <div class="mc-meta">기준 ${asOf} · Fed 총자산 - TGA - RRP</div>`;

    grid.appendChild(card);
    requestAnimationFrame(() => drawMacroArea(chartId, nlData.chart_data || [], isUp, 120));
}

function drawMacroArea(chartId, rows, isUp, height) {
    const container = document.getElementById(chartId);
    if (!container || !rows.length || typeof LightweightCharts === 'undefined') return;
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth, height,
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#999' },
        grid: { vertLines: { visible: false }, horzLines: { visible: false } },
        rightPriceScale: { visible: false }, timeScale: { visible: false, borderVisible: false },
        handleScroll: false, handleScale: false,
    });
    const series = chart.addAreaSeries({
        topColor: isUp ? 'rgba(0,200,83,.12)' : 'rgba(240,68,82,.12)',
        bottomColor: 'transparent', lineColor: isUp ? '#00C853' : '#F04452',
        lineWidth: 2, priceLineVisible: false, crosshairMarkerVisible: false,
    });
    series.setData(rows);
    chart.timeScale().fitContent();
    bindResponsiveChart(container, chart, height);
}

function renderMacroGrid(indicators) {
    const grid = document.getElementById('macro-grid');
    if (!grid) return;
    const loading = grid.querySelector('.macro-loading-inner');
    if (loading) loading.remove();

    indicators.forEach((item, index) => {
        const symbol = item.original_symbol || item.symbol;
        const hasChart = Array.isArray(item.chart_data) && item.chart_data.length > 0;
        const isUp = Number(item.delta ?? item.change) >= 0;
        const chartId = `macro-chart-${index}`;
        const card = document.createElement('div');
        card.className = `macro-card ${item.stale ? 'macro-card-stale' : ''}`;
        card.tabIndex = item.link ? 0 : -1;
        card.setAttribute('role', item.link ? 'link' : 'group');
        card.setAttribute('aria-label', `${item.name}, 기준 ${item.asOf || '-'}`);

        const open = () => { if (item.link) window.open(item.link, '_blank', 'noopener'); };
        card.addEventListener('click', open);
        card.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
        });

        card.innerHTML = `
            <div class="mc-header">
                <span class="mc-name">${item.name}${item.stale ? ' <span class="stale-badge">STALE</span>' : ''} <span class="link-icon">↗</span></span>
                <span class="mc-symbol">${symbol}</span>
            </div>
            <div class="mc-value-row">
                <span class="mc-value">${formatMacroValue(item)}</span>
                <span class="mc-change ${isUp ? 'up' : 'down'}">${formatMacroChange(item)}</span>
            </div>
            <div class="mc-chart-wrapper">
                <div id="${chartId}" class="mc-mini-chart">${hasChart ? '' : '<div class="no-chart">시계열 없음</div>'}</div>
                ${hasChart ? `<div class="mc-chart-dates"><span>${item.chart_data[0]?.time || ''}</span><span>${item.asOf || item.chart_data.at(-1)?.time || ''}</span></div>` : ''}
            </div>
            <div class="mc-desc">${item.desc}</div>
            <div class="mc-meta">기준 ${item.asOf || '-'} · ${item.source || '공개 경제데이터'}</div>`;

        grid.appendChild(card);
        if (hasChart) requestAnimationFrame(() => drawMacroLine(chartId, item.chart_data, isUp, symbol));
    });
}

function drawMacroLine(chartId, rows, isUp, symbol) {
    const container = document.getElementById(chartId);
    if (!container || typeof LightweightCharts === 'undefined') return;
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth, height: 80,
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#999' },
        grid: { vertLines: { visible: false }, horzLines: { visible: false } },
        rightPriceScale: { visible: false }, timeScale: { visible: false, borderVisible: false },
        handleScroll: false, handleScale: false,
    });
    let lineColor = isUp ? '#F04452' : '#3182F6';
    if (symbol === '^VIX' || symbol === 'T10YIE' || symbol === 'DFII10') {
        lineColor = isUp ? '#F04452' : '#3182F6';
    }
    const series = chart.addLineSeries({ color: lineColor, lineWidth: 2, priceLineVisible: false, crosshairMarkerVisible: false });
    series.setData(rows);
    chart.timeScale().fitContent();
    bindResponsiveChart(container, chart, 80);
}
