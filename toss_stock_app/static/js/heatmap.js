/**
 * 히트맵 시각화 로직
 */

document.addEventListener('DOMContentLoaded', () => {
    // 탭 전환 이벤트 리스너가 이미 fwdper.js 나 chart.js 에 있을 수 있음
    // 통합 관리를 위해 탭 버튼 클릭 시 히트맵 로드 트리거
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.getAttribute('data-tab');
            if (tab === 'heatmap') {
                loadHeatmapData();
            }
        });
    });
});

async function loadHeatmapData() {
    const container = document.getElementById('heatmap-container');
    if (!container) return;

    // 로딩 상태
    container.innerHTML = '<div class="heatmap-loading"><div class="spinner"></div><p>실시간 시장 데이터를 분석 중입니다...</p></div>';

    try {
        const res = await fetch('/api/heatmap');
        const data = await res.json();

        if (data.results && data.results.length > 0) {
            renderHeatmap(data.results);
        } else {
            container.innerHTML = '<div class="heatmap-error">데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</div>';
        }
    } catch (e) {
        console.error('Heatmap load error:', e);
        container.innerHTML = '<div class="heatmap-error">서버 연결에 실패했습니다.</div>';
    }
}

function renderHeatmap(stocks) {
    const container = document.getElementById('heatmap-container');
    container.innerHTML = '';

    // 시가총액 순 정렬 (박스 크기 조절용으로 쓸 수 있음)
    stocks.sort((a, b) => b.marketCap - a.marketCap);

    stocks.forEach(stock => {
        const box = document.createElement('div');
        box.className = 'heatmap-box';

        // 수익률에 따른 색상 결정
        const change = stock.change;
        let colorClass = 'neutral';
        if (change >= 3) colorClass = 'up-deep';
        else if (change >= 0.5) colorClass = 'up';
        else if (change <= -3) colorClass = 'down-deep';
        else if (change <= -0.5) colorClass = 'down';

        box.classList.add(colorClass);

        // 박스 내부 구성
        box.innerHTML = `
            <div class="hb-ticker">${stock.ticker.split('.')[0]}</div>
            <div class="hb-change">${change > 0 ? '+' : ''}${change}%</div>
            <div class="hb-name">${stock.name}</div>
        `;

        // 클릭 시 차트 탭으로 이동해서 해당 종목 보여주는 기능 등 추가 가능
        box.onclick = () => {
            alert(`${stock.name} (${stock.ticker}): ${stock.price} USD, 변동률: ${change}%`);
        };

        container.appendChild(box);
    });
}
