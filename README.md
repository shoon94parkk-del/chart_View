# 토스 스타일 주식 비교 차트

한국·미국 종목을 비교하고 밸류에이션, 애널리스트 컨센서스, 기술 조건과 거시지표를 함께 확인하는 모바일 웹앱입니다.

## 🚀 주요 기능

- **멀티 종목 비교** - 최대 6개 종목의 조정주가 수익률 비교
- **밸류에이션** - 종합 지표, 공시 시점 근사 역사적 밴드, 실적 컨센서스
- **투자판단 보조** - 가치·수익성·전망·모멘텀 근거를 분리해 표시
- **종목 발굴** - KOSPI·KOSDAQ 장마감 스크리너와 EPS 상향·주가 약세 후보
- **시장 화면** - 실시간성 시세와 사전 계산된 거시지표의 기준일을 구분
- **관심종목** - 브라우저 기기에 저장되는 관심종목과 최근 본 종목
- **모바일 최적화** - 하단 5개 메뉴, 터치 친화적 화면, 브라우저 뒤로가기 지원

## 📦 설치

```bash
pip install -r requirements.txt
```

## ▶️ 실행

```bash
uvicorn main:app --host 0.0.0.0 --port 8080
```

## 🌐 배포

### Render.com (무료)
1. GitHub에 푸시
2. [render.com](https://render.com) 가입
3. New → Web Service → GitHub 연결
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Railway (무료)
1. [railway.app](https://railway.app) 가입
2. New Project → Deploy from GitHub
3. 자동 감지 후 배포

## 📁 파일 구조

```
├── main.py              # FastAPI 서버
├── requirements.txt     # 의존성
├── static/
│   ├── css/style.css    # 토스 스타일 CSS
│   └── js/chart.js      # Lightweight Charts 로직
└── templates/
    └── index.html       # 메인 HTML
```

## 📱 스크린샷

토스 디자인 시스템 기반의 깔끔한 UI

## 🔧 기술 스택

- FastAPI
- TradingView Lightweight Charts
- yfinance
- Pretendard 폰트

## 데이터 기준

- 비교 차트는 Yahoo Chart의 조정주가 일봉을 우선 사용합니다.
- 시세 수집 시각과 원자료 거래일·발표일은 서로 구분합니다.
- 예상 PER/EPS는 공급자가 제공한 예상 구간이며, 회계기간을 독립적으로 확인하지 못한 경우 화면에 그렇게 표시합니다.
- 역사적 PER/PBR은 과거 가격과 재무자료를 결합한 근사 재구성치입니다.

현재 운영·배포 구조와 다음 작업 순서는 `docs/handover.md`, 필드 정의는 `docs/data-definitions.md`, 버전별 변경은 `CHANGELOG.md`를 확인하세요.
