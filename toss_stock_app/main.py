"""
토스 미니앱 - 주식 비교 차트
FastAPI 서버 (토스 가이드라인 준수)
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import requests
import pandas as pd
import io
import time
import base64
import asyncio
import os
import threading

# 전역 캐시 (메모리)
MACRO_CACHE = {
    "data": None,
    "timestamp": 0
}
STOCK_INFO_CACHE = {}  # {ticker: {"name": str, "timestamp": float}}
CACHE_EXPIRE = 3600 * 6  # 6시간 캐시

app = FastAPI(title="주식 비교 차트", version="1.0.0")

# CORS 설정 - 토스 앱인토스 도메인 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chartview.apps.tossmini.com",        # 실제 서비스 환경
        "https://chartview.private-apps.tossmini.com", # 콘솔 QR 테스트 환경
        "*",  # 개발용 (프로덕션에서는 제거 권장)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 및 템플릿
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ========================
# Health Check & Self-Ping (Render 절전 방지)
# ========================
@app.get("/health")
async def health_check():
    """Health check 엔드포인트"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

def self_ping_worker():
    """14분마다 자기 서버에 Ping 전송 (Render 슬립 방지)"""
    # Render 환경에서만 동작 (RENDER_EXTERNAL_URL 환경변수 존재 시)
    base_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not base_url:
        print("[Self-Ping] RENDER_EXTERNAL_URL not set, skipping self-ping (local dev)")
        return
    
    ping_url = f"{base_url}/health"
    print(f"[Self-Ping] Started - will ping {ping_url} every 14 minutes")
    
    while True:
        time.sleep(840)  # 14분 = 840초
        try:
            r = requests.get(ping_url, timeout=10)
            print(f"[Self-Ping] Keep-Alive Ping sent -> {r.status_code} at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[Self-Ping] Ping failed: {e}")

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 Self-Ping 백그라운드 스레드 시작"""
    ping_thread = threading.Thread(target=self_ping_worker, daemon=True)
    ping_thread.start()


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ========================
# 한국 주식 검색 (KRX 종목 리스트)
# ========================
KRX_STOCK_LIST = []  # [{code, name}, ...]
KRX_CACHE_TIME = 0

def load_krx_stock_list():
    """KRX 전체 종목 리스트 로드 (KOSPI + KOSDAQ)"""
    global KRX_STOCK_LIST, KRX_CACHE_TIME
    
    # 24시간 캐시
    if KRX_STOCK_LIST and (time.time() - KRX_CACHE_TIME < 86400):
        return KRX_STOCK_LIST
    
    try:
        # KRX 종목 리스트를 krx.co.kr에서 가져오기
        headers = {"User-Agent": "Mozilla/5.0"}
        
        all_stocks = []
        
        # KOSPI
        for market_type in ["stockMkt", "kosdaqMkt"]:
            url = "http://kind.krx.co.kr/corpgeneral/corpList.do"
            params = {"method": "download", "marketType": market_type}
            try:
                res = requests.get(url, params=params, headers=headers, timeout=10)
                df = pd.read_html(io.StringIO(res.text))[0]
                for _, row in df.iterrows():
                    code = str(row["종목코드"]).zfill(6)
                    name = str(row["회사명"]).strip()
                    all_stocks.append({"code": code, "name": name})
            except Exception as e:
                print(f"[KRX] Failed to load {market_type}: {e}")
        
        if all_stocks:
            KRX_STOCK_LIST = all_stocks
            KRX_CACHE_TIME = time.time()
            print(f"[KRX] Loaded {len(all_stocks)} Korean stocks")
        
        return KRX_STOCK_LIST
    except Exception as e:
        print(f"[KRX] Error loading stock list: {e}")
        return KRX_STOCK_LIST


@app.get("/api/search")
async def search_stocks(q: str):
    """종목 검색 API - 한국 주식 이름 및 글로벌 티커 검색"""
    query = q.strip()
    if not query:
        return {"results": []}
    
    results = []
    
    # 1. 한국어가 포함되어 있으면 KRX에서 검색
    has_korean = any('\uac00' <= c <= '\ud7a3' for c in query)
    
    if has_korean:
        krx_list = load_krx_stock_list()
        
        # 정확히 일치하는 것 먼저
        exact = [s for s in krx_list if s["name"] == query]
        # 포함하는 것
        partial = [s for s in krx_list if query in s["name"] and s not in exact]
        
        matches = (exact + partial)[:10]
        
        for stock in matches:
            # Yahoo Finance 형식: 6자리코드.KS (KOSPI) 또는 .KQ (KOSDAQ)
            # 먼저 .KS로 시도, 실패 시 .KQ
            yahoo_ticker = f"{stock['code']}.KS"
            results.append({
                "symbol": yahoo_ticker,
                "name": stock["name"],
                "type": "KRX"
            })
    else:
        # 2. 영문 입력: yfinance로 직접 검색 시도
        query_upper = query.upper()
        
        # 먼저 KRX에서 코드 검색 (숫자 6자리 입력 시)
        if query.isdigit() and len(query) == 6:
            krx_list = load_krx_stock_list()
            code_match = [s for s in krx_list if s["code"] == query]
            if code_match:
                results.append({
                    "symbol": f"{query}.KS",
                    "name": code_match[0]["name"],
                    "type": "KRX"
                })
        
        # yfinance로 티커 검색
        try:
            ticker = yf.Ticker(query_upper)
            info = ticker.info
            name = info.get("shortName") or info.get("longName") or query_upper
            if info.get("regularMarketPrice") or info.get("previousClose"):
                results.append({
                    "symbol": query_upper,
                    "name": name,
                    "type": "GLOBAL"
                })
        except:
            pass
        
        # 결과가 없으면 그대로 반환
        if not results:
            results.append({
                "symbol": query_upper,
                "name": query_upper,
                "type": "UNKNOWN"
            })
    
    return {"results": results}


def get_korean_stock_name(ticker):
    """네이버 금융에서 한국 주식 한글 이름 가져오기"""
    try:
        from bs4 import BeautifulSoup
        code = ticker.split(".")[0]
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        name_tag = soup.select_one("div.wrap_company h2 a")
        if name_tag:
            name = name_tag.get_text(strip=True)
            if name:
                return name
    except Exception as e:
        print(f"[Naver Name] Failed for {ticker}: {e}")
    return None


@app.get("/api/compare")
async def compare_stocks(tickers: str, period: str = "1mo", start: str = None, end: str = None):
    """여러 종목 비교 API (날짜 범위 지원)"""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    
    if not ticker_list:
        return JSONResponse({"error": "종목을 입력해주세요"}, status_code=400)
    
    # 기간별 인터벌
    interval_map = {
        "1d": "5m", "5d": "15m", "1mo": "1h",
        "3mo": "1d", "6mo": "1d", "1y": "1d", "max": "1d"
    }
    interval = interval_map.get(period, "1d")
    
    results = []
    
    async def fetch_stock_data(ticker):
        # 캐시 확인 (이름 정보 등)
        cached = STOCK_INFO_CACHE.get(ticker)
        now_ts = time.time()
        
        try:
            stock = yf.Ticker(ticker)
            
            # 날짜 범위가 있으면 사용, 없으면 기간 사용
            if start and end:
                df = stock.history(start=start, end=end, interval="1d")
            else:
                df = stock.history(period=period, interval=interval)
            
            if df.empty:
                return None
            
            # 이름 정보 캐싱 (가장 느린 부분)
            if cached and (now_ts - cached["timestamp"] < CACHE_EXPIRE):
                name = cached["name"]
            else:
                is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
                name = ticker
                
                if is_korean:
                    # 한국 주식: 네이버 금융에서 한글 이름 가져오기
                    name = get_korean_stock_name(ticker) or ticker
                
                if name == ticker:
                    # 글로벌 주식 또는 네이버 실패 시 yfinance 사용
                    info = stock.info
                    name = info.get("shortName") or info.get("longName") or ticker
                
                STOCK_INFO_CACHE[ticker] = {"name": name, "timestamp": now_ts}
            
            # 수익률 계산
            first = df["Close"].iloc[0]
            line_data = [{"time": int(idx.timestamp()), "value": round(((row["Close"] - first) / first) * 100, 2)} 
                         for idx, row in df.iterrows()]
            
            return {
                "ticker": ticker,
                "name": name,
                "price": round(df["Close"].iloc[-1], 2),
                "return": round(((df["Close"].iloc[-1] - first) / first) * 100, 2),
                "data": line_data
            }
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            return None

    # 병렬 실행 (최대 6종목)
    tasks = [fetch_stock_data(t) for t in ticker_list[:6]]
    fetch_results = await asyncio.gather(*tasks)
    results = [r for r in fetch_results if r]
    
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return {
        "stocks": results,
        "timestamp": now,
        "source": "Yahoo Finance"
    }


@app.get("/api/popular")
async def popular():
    """인기 종목"""
    return {
        "us": [
            {"symbol": "AAPL", "name": "Apple"},
            {"symbol": "MSFT", "name": "Microsoft"},
            {"symbol": "GOOGL", "name": "Google"},
            {"symbol": "NVDA", "name": "NVIDIA"},
            {"symbol": "TSLA", "name": "Tesla"},
            {"symbol": "AMZN", "name": "Amazon"},
        ],
        "kr": [
            {"symbol": "005930.KS", "name": "삼성전자"},
            {"symbol": "000660.KS", "name": "SK하이닉스"},
            {"symbol": "035420.KS", "name": "NAVER"},
            {"symbol": "035720.KS", "name": "카카오"},
        ]
    }


# 종목 검색용 데이터베이스
STOCK_DATABASE = [
    # 한국 주요 종목
    {"symbol": "005930.KS", "name": "삼성전자", "keywords": "samsung electronics 삼전"},
    {"symbol": "000660.KS", "name": "SK하이닉스", "keywords": "sk hynix 하이닉스"},
    {"symbol": "035420.KS", "name": "NAVER", "keywords": "네이버 naver"},
    {"symbol": "035720.KS", "name": "카카오", "keywords": "kakao"},
    {"symbol": "006400.KS", "name": "삼성SDI", "keywords": "samsung sdi 삼성에스디아이"},
    {"symbol": "051910.KS", "name": "LG화학", "keywords": "lg chem 엘지화학"},
    {"symbol": "373220.KS", "name": "LG에너지솔루션", "keywords": "lg energy solution 엘지에너지"},
    {"symbol": "005380.KS", "name": "현대차", "keywords": "hyundai motor 현대자동차"},
    {"symbol": "000270.KS", "name": "기아", "keywords": "kia 기아차"},
    {"symbol": "068270.KS", "name": "셀트리온", "keywords": "celltrion"},
    {"symbol": "207940.KS", "name": "삼성바이오로직스", "keywords": "samsung biologics 삼바"},
    {"symbol": "003670.KS", "name": "포스코퓨처엠", "keywords": "posco future m 포스코"},
    {"symbol": "028260.KS", "name": "삼성물산", "keywords": "samsung c&t 삼성건설"},
    {"symbol": "018260.KS", "name": "삼성에스디에스", "keywords": "samsung sds 삼성SDS"},
    {"symbol": "009150.KS", "name": "삼성전기", "keywords": "samsung electro-mechanics"},
    {"symbol": "066570.KS", "name": "LG전자", "keywords": "lg electronics 엘지전자"},
    {"symbol": "003550.KS", "name": "LG", "keywords": "lg corp 엘지"},
    {"symbol": "105560.KS", "name": "KB금융", "keywords": "kb financial 국민은행"},
    {"symbol": "055550.KS", "name": "신한지주", "keywords": "shinhan 신한은행"},
    {"symbol": "086790.KS", "name": "하나금융지주", "keywords": "hana financial 하나은행"},
    # 미국 주요 종목
    {"symbol": "AAPL", "name": "Apple", "keywords": "애플 아이폰 iphone"},
    {"symbol": "MSFT", "name": "Microsoft", "keywords": "마이크로소프트 윈도우"},
    {"symbol": "GOOGL", "name": "Alphabet (Google)", "keywords": "구글 알파벳 youtube"},
    {"symbol": "AMZN", "name": "Amazon", "keywords": "아마존 aws"},
    {"symbol": "NVDA", "name": "NVIDIA", "keywords": "엔비디아 GPU 그래픽"},
    {"symbol": "META", "name": "Meta (Facebook)", "keywords": "메타 페이스북 인스타그램"},
    {"symbol": "TSLA", "name": "Tesla", "keywords": "테슬라 전기차"},
    {"symbol": "AMD", "name": "AMD", "keywords": "에이엠디 라이젠"},
    {"symbol": "INTC", "name": "Intel", "keywords": "인텔 cpu"},
    {"symbol": "NFLX", "name": "Netflix", "keywords": "넷플릭스"},
    {"symbol": "DIS", "name": "Disney", "keywords": "디즈니"},
    {"symbol": "JPM", "name": "JPMorgan Chase", "keywords": "제이피모건"},
    {"symbol": "V", "name": "Visa", "keywords": "비자"},
    {"symbol": "MA", "name": "Mastercard", "keywords": "마스터카드"},
    {"symbol": "BAC", "name": "Bank of America", "keywords": "뱅크오브아메리카"},
    {"symbol": "GS", "name": "Goldman Sachs", "keywords": "골드만삭스"},
    {"symbol": "UNH", "name": "UnitedHealth", "keywords": "유나이티드헬스"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "keywords": "존슨앤존슨"},
    {"symbol": "PFE", "name": "Pfizer", "keywords": "화이자"},
    {"symbol": "LLY", "name": "Eli Lilly", "keywords": "일라이릴리"},
    {"symbol": "XOM", "name": "ExxonMobil", "keywords": "엑슨모빌"},
    {"symbol": "CVX", "name": "Chevron", "keywords": "쉐브론"},
    {"symbol": "KO", "name": "Coca-Cola", "keywords": "코카콜라"},
    {"symbol": "PEP", "name": "PepsiCo", "keywords": "펩시콜라"},
    {"symbol": "MCD", "name": "McDonald's", "keywords": "맥도날드"},
    {"symbol": "SBUX", "name": "Starbucks", "keywords": "스타벅스"},
    {"symbol": "NKE", "name": "Nike", "keywords": "나이키"},
    {"symbol": "BA", "name": "Boeing", "keywords": "보잉"},
    {"symbol": "CAT", "name": "Caterpillar", "keywords": "캐터필러"},
    # ETF
    {"symbol": "SPY", "name": "S&P 500 ETF", "keywords": "sp500 에스피"},
    {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "keywords": "나스닥 큐큐큐"},
    {"symbol": "GLD", "name": "Gold ETF", "keywords": "금 골드"},
    {"symbol": "SLV", "name": "Silver ETF", "keywords": "은 실버"},
    {"symbol": "USO", "name": "Oil ETF", "keywords": "원유 오일"},
]


@app.get("/api/search")
async def search_ticker(q: str):
    """종목 검색 API"""
    if not q or len(q) < 1:
        return {"results": []}
    
    query = q.lower()
    results = []
    
    for stock in STOCK_DATABASE:
        # 심볼, 이름, 키워드에서 검색
        if (query in stock["symbol"].lower() or 
            query in stock["name"].lower() or 
            query in stock.get("keywords", "").lower()):
            results.append({
                "symbol": stock["symbol"],
                "name": stock["name"]
            })
    
    return {"results": results[:10]}


@app.get("/api/heatmap")
async def heatmap_data():
    """히트맵용 주요 종목 데이터 API"""
    # 히트맵에 표시할 주요 종목 리스트
    heatmap_tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
        "JPM", "V", "MA", "UNH", "JNJ", "LLY", "XOM", "AVGO",
        "005930.KS", "000660.KS", "035420.KS", "035720.KS", "005380.KS"
    ]
    
    def fetch_change(ticker):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            # regularMarketChangePercent 또는 trailingPegRatio 등은 실시간성에 따라 다를 수 있음
            # 간단하게 previousClose와 currentPrice 비교
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            prev = info.get("regularMarketPreviousClose")
            
            if current and prev:
                change = ((current - prev) / prev) * 100
                return {
                    "ticker": ticker,
                    "name": info.get("shortName") or ticker,
                    "change": round(change, 2),
                    "price": current,
                    "marketCap": info.get("marketCap", 0)
                }
        except:
            return None
        return None

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_change, t): t for t in heatmap_tickers}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
    
    return {"results": results}

def compute_net_liquidity(ordered_results):
    """순유동성(Net Liquidity) = WALCL - WTREGEN - RRPONTSYD 계산"""
    # 각 지표의 chart_data를 {날짜: 값} 딕셔너리로 변환
    series = {}
    for item in ordered_results:
        sym = item.get("original_symbol", item.get("symbol"))
        if sym in ("WALCL", "WTREGEN", "RRPONTSYD"):
            data = item.get("chart_data", [])
            series[sym] = {d["time"]: d["value"] for d in data}
    
    if not all(k in series for k in ("WALCL", "WTREGEN", "RRPONTSYD")):
        return {"error": True, "message": "순유동성 계산에 필요한 지표(WALCL, WTREGEN, RRPONTSYD) 중 일부를 가져오지 못했습니다.", "chart_data": []}
    
    # 모든 날짜 합치기
    all_dates = sorted(set(list(series["WALCL"].keys()) + list(series["WTREGEN"].keys()) + list(series["RRPONTSYD"].keys())))
    
    if not all_dates:
        return {"error": True, "message": "시계열 데이터가 비어 있습니다.", "chart_data": []}
    
    # Forward-fill 방식으로 날짜 병합 후 계산
    chart_data = []
    last = {"WALCL": None, "WTREGEN": None, "RRPONTSYD": None}
    
    for date in all_dates:
        for sym in ("WALCL", "WTREGEN", "RRPONTSYD"):
            if date in series[sym]:
                last[sym] = series[sym][date]
        
        if all(v is not None for v in last.values()):
            # WALCL은 백만달러, WTREGEN도 백만달러, RRPONTSYD는 10억달러 단위
            # FRED 기준: WALCL(백만$), WTREGEN(백만$), RRPONTSYD(십억$)
            # 통일을 위해 RRPONTSYD를 백만 단위로 변환 (×1000)
            net = last["WALCL"] - last["WTREGEN"] - (last["RRPONTSYD"] * 1000)
            chart_data.append({"time": date, "value": round(net, 2)})
    
    if not chart_data:
        return {"error": True, "message": "날짜 병합 후 유효한 데이터가 없습니다.", "chart_data": []}
    
    current_val = chart_data[-1]["value"]
    prev_val = chart_data[-2]["value"] if len(chart_data) > 1 else current_val
    change = ((current_val - prev_val) / abs(prev_val)) * 100 if prev_val != 0 else 0.0
    
    return {
        "error": False,
        "name": "순유동성 (Net Liquidity)",
        "symbol": "NET_LIQ",
        "desc": "연준 총자산에서 TGA와 역래포를 뺀 실질 유동성. 이 값이 증가하면 시장에 돈이 풀리고 있다는 의미이며, 주가에 우호적입니다.",
        "value": round(current_val, 0),
        "change": round(change, 2),
        "chart_data": chart_data,
        "link": "https://fred.stlouisfed.org/series/WALCL"
    }


def generate_macro_summary(ordered_results, net_liquidity):
    """모든 경제 지표를 종합 분석하여 한줄 요약 + 신호등 생성"""
    
    # 지표별 점수: -2(매우 부정) ~ +2(매우 긍정)
    scores = {}
    details = []
    
    for item in ordered_results:
        sym = item.get("original_symbol", item.get("symbol"))
        val = item.get("value", 0)
        is_error = item.get("error", False)
        if is_error or val == 0:
            continue
        
        if sym == "T10Y2Y":
            # 장단기 금리차: 0 이하=역전(위험), 0~0.3=좁음(주의), 0.3+=정상
            if val < 0:
                scores["금리차"] = -2
                details.append("금리역전⚠️")
            elif val < 0.3:
                scores["금리차"] = -1
                details.append("금리차 좁음")
            else:
                scores["금리차"] = 1
                details.append("금리차 정상")
        
        elif sym == "^VIX":
            if val > 30:
                scores["VIX"] = -2
                details.append(f"VIX {val:.0f} 공포🔴")
            elif val > 20:
                scores["VIX"] = -1
                details.append(f"VIX {val:.0f} 경계")
            elif val > 15:
                scores["VIX"] = 0
                details.append(f"VIX {val:.0f} 보통")
            else:
                scores["VIX"] = 2
                details.append(f"VIX {val:.0f} 안정🟢")
        
        elif sym == "BAMLH0A0HYM2":
            # 하이일드 스프레드: 5+심각, 4~5주의, ~4정상
            if val > 5:
                scores["신용"] = -2
                details.append("신용스프레드 확대⚠️")
            elif val > 4:
                scores["신용"] = -1
                details.append("신용스프레드 주의")
            else:
                scores["신용"] = 1
                details.append("신용스프레드 안정")
        
        elif sym == "FEDFUNDS":
            if val >= 5:
                scores["금리"] = -1
                details.append(f"기준금리 {val:.1f}% 긴축")
            elif val >= 3:
                scores["금리"] = 0
                details.append(f"기준금리 {val:.1f}%")
            elif val <= 2:
                scores["금리"] = 1
                details.append(f"기준금리 {val:.1f}% 완화")
        
        elif sym == "T10YIE":
            # 기대인플레이션: 2.5%+높음, 2~2.5보통, ~2낮음
            if val > 2.5:
                scores["인플레"] = -1
                details.append(f"기대인플레 {val:.1f}%↑")
            elif val >= 2.0:
                scores["인플레"] = 0
                details.append(f"기대인플레 {val:.1f}%")
            else:
                scores["인플레"] = 1
                details.append(f"기대인플레 {val:.1f}%↓")
        
        elif sym == "DGS10":
            # 10년물 금리
            if val > 4.5:
                scores["장기금리"] = -1
                details.append(f"10Y {val:.1f}% 고금리")
            elif val > 3.5:
                scores["장기금리"] = 0
                details.append(f"10Y {val:.1f}%")
            else:
                scores["장기금리"] = 1
                details.append(f"10Y {val:.1f}% 저금리")
        
        elif sym == "M2SL":
            change = item.get("change", 0)
            if change > 0.5:
                scores["M2"] = 1
                details.append("M2 통화량↑")
            elif change < -0.5:
                scores["M2"] = -1
                details.append("M2 통화량↓")
    
    # 순유동성Liquidity)
    if net_liquidity and not net_liquidity.get("error"):
        nl_change = net_liquidity.get("change", 0)
        if nl_change > 1:
            scores["유동성"] = 2
            details.append(f"순유동성 +{nl_change:.1f}%🟢")
        elif nl_change > 0:
            scores["유동성"] = 1
            details.append(f"순유동성 +{nl_change:.1f}%")
        elif nl_change > -1:
            scores["유동성"] = -1
            details.append(f"순유동성 {nl_change:.1f}%")
        else:
            scores["유동성"] = -2
            details.append(f"순유동성 {nl_change:.1f}%🔴")
    
    # 종합 점수 계산
    if not scores:
        return {"text": "지표 데이터를 가져오는 중입니다.", "level": "yellow"}
    
    total_score = sum(scores.values())
    max_possible = len(scores) * 2
    min_possible = len(scores) * -2
    
    # 점수 비율 (-1.0 ~ +1.0)
    if max_possible > 0:
        ratio = total_score / max_possible if total_score >= 0 else total_score / abs(min_possible)
    else:
        ratio = 0
    
    # 신호등 결정
    if total_score <= -3 or ratio <= -0.4:
        level = "red"
    elif total_score <= 0 or ratio <= 0.1:
        level = "yellow"
    else:
        level = "green"
    
    # 종합 판단문 생성
    detail_str = " | ".join(details[:6])  # 최대 6개 지표 표시
    
    if level == "red":
        judgment = "→ 리스크 관리가 필요한 시점입니다. 방어적 포지션을 고려하세요."
    elif level == "yellow":
        judgment = "→ 혼조세입니다. 선별적 접근과 모니터링이 필요합니다."
    else:
        judgment = "→ 전반적으로 자산시장에 우호적인 환경입니다."
    
    text = f"{detail_str} {judgment}"
    
    return {"text": text, "level": level}


@app.get("/api/macro")
async def macro_data():
    """FRED 및 주요 글로벌 매크로 지표 (10종 패키지)"""
    global MACRO_CACHE
    current_time = time.time()
    
    # 1시간(3600초) 캐싱 - 빠른 로딩을 위해 이전 데이터를 기억
    if MACRO_CACHE["data"] and (current_time - MACRO_CACHE["timestamp"] < 3600):
        return MACRO_CACHE["data"]

    # 1. 지표 정의 (메르 스타일 10종)
    indicators = {
        "T10Y2Y": {
            "name": "장단기 금리차 (10Y-2Y)", 
            "desc": "경기 침체 신호등. 0 이하(역전)로 내려갔다가 다시 올라올 때 침체가 시작되는 경향이 있습니다.",
            "link": "https://fred.stlouisfed.org/series/T10Y2Y",
            "source": "FRED", "fallback": None
        },
        "T10Y3M": {
            "name": "장단기 금리차 (10Y-3M)", 
            "desc": "연준이 가장 신뢰하는 침체 지표. 이 수치가 마이너스면 연준의 긴축이 과도하다는 뜻입니다.",
            "link": "https://fred.stlouisfed.org/series/T10Y3M",
            "source": "FRED", "fallback": None
        },
        "BAMLH0A0HYM2": {
            "name": "하이일드 스프레드 (Risk)", 
            "desc": "기업 부도 위험. 이 그래프가 치솟으면 기업들의 자금줄이 마르고 있다는 강력한 경고입니다.",
            "link": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
            "source": "FRED", "fallback": "HYG"
        },
        "RRPONTSYD": {
            "name": "역래포 잔액 (Liquidity)", 
            "desc": "시장의 예비 자금. 이 돈이 줄어들면 시장에 유동성이 공급되어 주가 방어에 도움이 됩니다.",
            "link": "https://fred.stlouisfed.org/series/RRPONTSYD",
            "source": "FRED", "fallback": "BIL"
        },
        "DFII10": {
            "name": "10년 실질금리 (TIPS)", 
            "desc": "인플레이션을 뺀 진짜 금리. 이 금리가 높으면(플러스) 자산 시장(주식, 부동산)은 하락 압력을 받습니다.",
            "link": "https://fred.stlouisfed.org/series/DFII10",
            "source": "FRED", "fallback": "TIP"
        },
        "T10YIE": {
            "name": "기대인플레이션 (BEI)", 
            "desc": "향후 10년 물가 예상치. 연준의 목표(2%)보다 높으면 금리 인하가 지연될 수 있습니다.",
            "link": "https://fred.stlouisfed.org/series/T10YIE",
            "source": "FRED", "fallback": None
        },
        "UNRATE": {
            "name": "실업률 (Unemployment)", 
            "desc": "실물 경기 바닥 신호. 실업률이 저점에서 0.5%p 이상 오르면(삼의 법칙) 침체 초기입니다.",
            "link": "https://fred.stlouisfed.org/series/UNRATE",
            "source": "FRED", "fallback": None
        },
        "RSAFS": {
            "name": "소매판매 (Retail Sales)", 
            "desc": "미국 경제의 70%인 소비의 힘. 소비가 꺾이면 기업 실적이 나빠지고 경기 침체가 옵니다.",
            "link": "https://fred.stlouisfed.org/series/RSAFS",
            "source": "FRED", "fallback": "XRT"
        },
        "WALCL": {
            "name": "연준 총자산 (Fed Balance)", 
            "desc": "연준이 푼 돈의 총량(QT/QE). 그래프가 꺾여 내려가면 시장 유동성이 줄어들고 있다는 뜻입니다.",
            "link": "https://fred.stlouisfed.org/series/WALCL",
            "source": "FRED", "fallback": "BTC-USD"
        },
        "WTREGEN": {
            "name": "재무부 일반계정 (TGA)", 
            "desc": "미 재무부가 보유한 현금. TGA가 줄어들면 시장에 유동성이 공급되고, 늘어나면 유동성이 흡수됩니다.",
            "link": "https://fred.stlouisfed.org/series/WTREGEN",
            "source": "FRED", "fallback": None
        },
        "M2SL": {
            "name": "M2 통화량 (Money Supply)", 
            "desc": "시중에 풀린 돈의 총량. M2가 증가하면 인플레이션 압력이 커지고, 감소하면 긴축 신호입니다.",
            "link": "https://fred.stlouisfed.org/series/M2SL",
            "source": "FRED", "fallback": None
        },
        "FEDFUNDS": {
            "name": "연방기금금리 (Fed Rate)", 
            "desc": "연준의 기준금리. 모든 금리의 기준이며, 인상 시 경기 긴축, 인하 시 경기 부양 신호입니다.",
            "link": "https://fred.stlouisfed.org/series/FEDFUNDS",
            "source": "FRED", "fallback": None
        },
        "^VIX": {
            "name": "공포 지수 (VIX)", 
            "desc": "투자 심리 지표. 20 이하면 평온, 30 이상이면 패닉 상태입니다.",
            "link": "https://finance.yahoo.com/quote/%5EVIX",
            "source": "YAHOO", "fallback": None
        },
    }

    # 2. 헬퍼 함수 정의
    def fetch_yahoo_fallback(symbol, info):
        """FRED 실패 시 야후 파이낸스 대체 지표 수집"""
        fallback_sym = info.get("fallback")
        # 대체제가 없어도 None 리턴 금지 -> 에러 객체 리턴
        if not fallback_sym: 
            return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}
        
        try:
            stock = yf.Ticker(fallback_sym)
            hist = stock.history(period="6mo")
            if hist.empty: 
                return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}
            
            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = ((current - prev) / prev) * 100
            chart_data = [{"time": t.strftime("%Y-%m-%d"), "value": round(v, 2)} for t, v in hist['Close'].items()]
            
            return {
                "original_symbol": symbol,
                "symbol": fallback_sym, 
                "name": info["name"] + " (대체)", 
                "desc": info["desc"] + " [FRED 접속 실패로 대체 지표]",
                "link": f"https://finance.yahoo.com/quote/{fallback_sym}",
                "value": round(current, 2), "change": round(change, 2),
                "chart_data": chart_data[-100:]
            }
        except: 
            return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}

    def fetch_fred_data(symbol, info):
        """FRED 공식 API 사용 (가장 확실한 방법)"""
        API_KEY = "e4549aea3557be8678ec41be06039285"
        base_url = "https://api.stlouisfed.org/fred/series/observations"
        
        try:
            # 최근 6개월 데이터만 요청 (차트에 최신 그래프 표시)
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
            params = {
                "series_id": symbol, "api_key": API_KEY, "file_type": "json",
                "sort_order": "asc",
                "observation_start": start_date
            }
            
            response = requests.get(base_url, params=params, timeout=5)
            # 400 Bad Request (존재하지 않는 심볼 등) 시 예외 발생 -> Catch -> Yahoo Fallback 시도
            response.raise_for_status() 
            
            data = response.json()
            observations = data.get("observations", [])
            
            if not observations: raise ValueError("No observations")

            chart_data = []
            for obs in observations:
                val = obs["value"]
                if val == ".": continue
                chart_data.append({"time": obs["date"], "value": float(val)})
            
            if not chart_data: raise ValueError("No valid data")
            
            current = chart_data[-1]["value"]
            prev = chart_data[-2]["value"] if len(chart_data) > 1 else current
            change = ((current - prev) / prev) * 100 if prev != 0 else 0.0
            
            return {
                "original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"],
                "value": round(current, 2), "change": round(change, 2), "chart_data": chart_data
            }
            
        except Exception as e:
            print(f"FRED API failed for {symbol}: {e} -> Trying Fallback")
            return fetch_yahoo_fallback(symbol, info) # 결과(성공/실패 객체)를 그대로 리턴

    def fetch_indicator(symbol, info):
        try:
            if info.get("source") == "FRED":
                return fetch_fred_data(symbol, info)

            # Yahoo 일반
            stock = yf.Ticker(symbol)
            hist = stock.history(period="6mo")
            if hist.empty: 
                return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}

            current, prev = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
            change = ((current - prev) / prev) * 100
            chart_data = [{"time": t.strftime("%Y-%m-%d"), "value": round(v, 2)} for t, v in hist['Close'].items()]
            
            return {
                "original_symbol": symbol,
                "symbol": symbol, "name": info["name"], "desc": info["desc"],
                "link": info["link"],
                "value": round(current, 2), "change": round(change, 2), "chart_data": chart_data[-100:]
            }
        except: 
            return {"original_symbol": symbol, "symbol": symbol, "name": info["name"], "desc": info["desc"], "link": info["link"], "value": 0, "change": 0, "chart_data": [], "error": True}

    # 3. 병렬 실행
    target_symbols = list(indicators.keys())
    results = []
    with ThreadPoolExecutor(max_workers=len(target_symbols)) as executor:
        futures = {executor.submit(fetch_indicator, s, indicators[s]): s for s in target_symbols}
        for future in as_completed(futures):
            res = future.result()
            if res: results.append(res)
    
    # 4. 정렬 (매우 중요: original_symbol 사용)
    ordered = [r for s in target_symbols for r in results if r.get('original_symbol') == s]
    
    # 5. 순유동성(Net Liquidity) 계산: WALCL - WTREGEN - RRPONTSYD
    net_liquidity = compute_net_liquidity(ordered)
    
    # 6. 한줄 요약 생성
    summary = generate_macro_summary(ordered, net_liquidity)
    
    response_data = {"results": ordered, "net_liquidity": net_liquidity, "summary": summary}
    MACRO_CACHE["data"] = response_data
    MACRO_CACHE["timestamp"] = current_time
    print(f"[MACRO] Fetched {len(ordered)} indicators + Net Liquidity, cached for 1 hour")
    
    return response_data



@app.get("/api/fwd-per")
@app.get("/api/valuation")
async def valuation_data(tickers: str):
    """밸류에이션 데이터 API - PER, PBR, PSR, EV/EBITDA, 배당수익률, ROE"""
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    
    if not ticker_list:
        return {"stocks": []}
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def fetch_naver_valuation(ticker):
        """네이버 금융에서 한국 주식 PER/PBR 가져오기 (yfinance 폴백)"""
        try:
            from bs4 import BeautifulSoup
            # 티커에서 종목코드 추출: 080220.KS -> 080220
            code = ticker.split(".")[0]
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, "html.parser")
            
            result = {}
            
            # 종목명
            name_tag = soup.select_one("div.wrap_company h2 a")
            if name_tag:
                result["name"] = name_tag.get_text(strip=True)
            
            # PER (id="_per"), PBR (id="_pbr"), 배당수익률 (id="_dvr")
            per_tag = soup.select_one("#_per")
            pbr_tag = soup.select_one("#_pbr")
            dvr_tag = soup.select_one("#_dvr")
            
            if per_tag:
                per_text = per_tag.get_text(strip=True).replace(",", "")
                if per_text and per_text != "N/A":
                    try: result["per"] = float(per_text)
                    except: pass
            
            if pbr_tag:
                pbr_text = pbr_tag.get_text(strip=True).replace(",", "")
                if pbr_text and pbr_text != "N/A":
                    try: result["pbr"] = float(pbr_text)
                    except: pass
            
            if dvr_tag:
                dvr_text = dvr_tag.get_text(strip=True).replace(",", "").replace("%", "")
                if dvr_text and dvr_text != "N/A":
                    try: result["dividendYield"] = float(dvr_text) / 100
                    except: pass
            
            if result:
                print(f"[Naver] {ticker}: PER={result.get('per')}, PBR={result.get('pbr')}")
            return result if result else None
        except Exception as e:
            print(f"[Naver] Failed for {ticker}: {e}")
            return None
    
    def fetch_valuation(ticker):
        """개별 종목 밸류에이션 데이터 가져오기"""
        now_ts = time.time()
        # 캐시 키는 지표를 포함하므로 'valuation_' 접두사 사용
        cache_key = f"val_{ticker.upper()}"
        cached = STOCK_INFO_CACHE.get(cache_key)
        
        if cached and (now_ts - cached["timestamp"] < CACHE_EXPIRE):
            return cached["data"]

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            name = info.get("shortName") or info.get("longName") or ticker
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            market_cap = info.get("marketCap", 0)
            sector = info.get("sector", "")
            
            # PER 등 주요 지표 수집
            trailing_pe = info.get("trailingPE")
            forward_pe = info.get("forwardPE")
            trailing_eps = info.get("trailingEps")
            forward_eps = info.get("forwardEps")
            pbr = info.get("priceToBook")
            book_value = info.get("bookValue")
            psr = info.get("priceToSalesTrailing12Months")
            
            ev = info.get("enterpriseValue")
            ebitda = info.get("ebitda")
            ev_ebitda = (ev / ebitda) if ev and ebitda and ebitda > 0 else None
            
            dividend_yield = info.get("dividendYield")
            roe = info.get("returnOnEquity")
            if roe is not None: roe = roe * 100
            
            operating_margin = info.get("operatingMargins")
            if operating_margin is not None: operating_margin = operating_margin * 100
            
            # 한국 주식 폴백: yfinance에서 PER/PBR이 없으면 네이버 금융에서 가져오기
            is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
            if is_korean and trailing_pe is None and pbr is None:
                naver_data = fetch_naver_valuation(ticker)
                if naver_data:
                    trailing_pe = trailing_pe or naver_data.get("per")
                    pbr = pbr or naver_data.get("pbr")
                    dividend_yield = dividend_yield or naver_data.get("dividendYield")
                    if naver_data.get("name"):
                        name = naver_data["name"]
            
            data = {
                "ticker": ticker,
                "name": name,
                "price": round(price, 2) if price else 0,
                "marketCap": market_cap,
                "sector": sector,
                "trailingPE": round(trailing_pe, 2) if trailing_pe else None,
                "forwardPE": round(forward_pe, 2) if forward_pe else None,
                "trailingEPS": round(trailing_eps, 2) if trailing_eps else None,
                "forwardEPS": round(forward_eps, 2) if forward_eps else None,
                "pbr": round(pbr, 2) if pbr else None,
                "bookValue": round(book_value, 2) if book_value else None,
                "psr": round(psr, 2) if psr else None,
                "evEbitda": round(ev_ebitda, 2) if ev_ebitda else None,
                "dividendYield": round(dividend_yield, 2) if dividend_yield else None,
                "roe": round(roe, 2) if roe else None,
                "operatingMargin": round(operating_margin, 2) if operating_margin else None,
            }
            # 캐시 저장
            STOCK_INFO_CACHE[cache_key] = {"data": data, "timestamp": now_ts}
            return data
        except Exception as e:
            print(f"Valuation Error: {ticker} - {e}")
            return None
    
    # 병렬 처리 (최대 10개)
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_valuation, t): t for t in ticker_list[:20]}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    
    # 입력 순서 유지
    ordered = []
    for t in ticker_list:
        for r in results:
            if r["ticker"].upper() == t.upper():
                ordered.append(r)
                break
    
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "stocks": ordered,
        "timestamp": now,
        "source": "Yahoo Finance"
    }


# ========================
# Gemini AI 질문 답변 API
# ========================
from pydantic import BaseModel

class AskRequest(BaseModel):
    question: str
    history: list = []  # 대화 히스토리 (선택)

# Gemini API 키 (환경변수 전용 - 코드에 키를 넣으면 Google이 유출로 감지합니다)
# 로컬: set GEMINI_API_KEYS=your_key_here (CMD) 또는 $env:GEMINI_API_KEYS="your_key_here" (PowerShell)
# Render: Environment Variables에서 GEMINI_API_KEYS 설정
_raw_keys = os.environ.get("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
if not GEMINI_API_KEYS:
    print("[WARNING] GEMINI_API_KEYS 환경변수 미설정. AI 채팅 비활성화.")
GEMINI_KEY_INDEX = 0

SYSTEM_PROMPT = """당신은 한국어 주식/경제 전문 AI 어시스턴트입니다.
다음 원칙을 따르세요:
1. 복잡한 경제 개념을 쉽고 직관적인 비유로 설명합니다.
2. 답변은 간결하되 핵심을 놓치지 않습니다. 불필요한 서론은 생략합니다.
3. 투자 조언이 아닌 '정보 제공'임을 명확히 합니다.
4. 데이터나 수치를 언급할 때는 출처(FRED, Yahoo Finance 등)를 명시합니다.
5. 마크다운 형식(굵은 글씨, 리스트, 이모지 등)을 활용해 가독성을 높입니다.
6. 한국 투자자 관점에서 환율, 원화 영향 등도 언급합니다.
7. 확실하지 않은 정보는 "~일 수 있습니다", "확인이 필요합니다" 등으로 표현합니다."""

import httpx
import json

@app.post("/api/ask")
async def ask_gemini(req: AskRequest):
    """Gemini AI에게 주식/경제 관련 질문 (스트리밍 지원)"""
    global GEMINI_KEY_INDEX
    
    question = req.question.strip()
    if not question:
        return JSONResponse({"error": "질문을 입력해주세요"}, status_code=400)
    
    if not GEMINI_API_KEYS:
        return JSONResponse({"error": "AI 서비스가 설정되지 않았습니다. 관리자에게 문의하세요."}, status_code=503)
    
    # 대화 히스토리 구성
    contents = []
    contents.append({"role": "user", "parts": [{"text": SYSTEM_PROMPT}]})
    contents.append({"role": "model", "parts": [{"text": "네, 주식/경제 전문 AI 어시스턴트입니다. 궁금한 점을 편하게 물어보세요!"}]})
    
    for msg in req.history[-10:]:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    
    contents.append({"role": "user", "parts": [{"text": question}]})

    async def generate():
        global GEMINI_KEY_INDEX
        last_error = ""
        
        for attempt in range(len(GEMINI_API_KEYS)):
            key_idx = (GEMINI_KEY_INDEX + attempt) % len(GEMINI_API_KEYS)
            api_key = GEMINI_API_KEYS[key_idx]
            
            # SSE 스트리밍 API URL (alt=sse로 안정적 파싱)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse&key={api_key}"
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.7,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                }
            }
            
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream("POST", url, json=payload) as response:
                        if response.status_code == 200:
                            GEMINI_KEY_INDEX = key_idx
                            async for line in response.aiter_lines():
                                # SSE 형식: "data: {...JSON...}"
                                if not line or not line.startswith("data: "):
                                    continue
                                try:
                                    json_str = line[6:]  # "data: " 제거
                                    chunk_data = json.loads(json_str)
                                    candidates = chunk_data.get("candidates", [])
                                    if candidates:
                                        parts = candidates[0].get("content", {}).get("parts", [])
                                        for part in parts:
                                            text = part.get("text", "")
                                            if text:
                                                yield text
                                except json.JSONDecodeError:
                                    continue
                            return  # 성공적으로 스트리밍 완료
                        elif response.status_code == 429:
                            last_error = f"API Key {key_idx+1} 할당량 초과"
                            continue
                        else:
                            body = await response.aread()
                            last_error = f"API 오류 {response.status_code}: {body.decode()[:200]}"
                            continue
            except Exception as e:
                last_error = str(e)
                continue
        
        yield f"에러 발생: {last_error}"

    return StreamingResponse(generate(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
