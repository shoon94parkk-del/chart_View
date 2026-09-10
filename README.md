# 토스 스타일 주식 비교 차트

여러 종목의 수익률을 한눈에 비교할 수 있는 모바일 최적화 웹앱입니다.

## 🚀 주요 기능

- **멀티 종목 비교** - 최대 6개 종목 동시 비교
- **섹터별 빠른 선택** - 빅테크, AI·반도체, ETF, 전기차, 한국 대표
- **날짜 범위 선택** - 원하는 기간 직접 설정
- **토스 스타일 UI** - 깔끔한 라이트 모드 디자인
- **모바일 최적화** - 핀치줌 비활성화, 터치 친화적

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
