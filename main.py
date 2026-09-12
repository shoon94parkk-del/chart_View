"""
토스 미니앱 - 주식 비교 차트
FastAPI 서버 (토스 가이드라인 준수)
"""

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
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
import re
from market_service import fetch_compare_stock, fetch_valuation_snapshot, fetch_quote_snapshot, fetch_history_series
from valuation_band_service import fetch_valuation_bands
from consensus_service import fetch_consensus

# 전역 캐시 (메모리)
MACRO_CACHE = {
    "data": None,
    "timestamp": 0
}
STOCK_INFO_CACHE = {}  # {ticker: {"name": str, "timestamp": float}}
CACHE_EXPIRE = 3600 * 6  # 6시간 캐시

# HOME V17 shared stale-while-revalidate snapshot.
# One successful load is reused by every visitor; refresh happens in the background.
HOME_SNAPSHOT_CACHE = {"data": None, "timestamp": 0.0, "refreshing": False}
HOME_SNAPSHOT_TTL = 60
HOME_SNAPSHOT_REFRESH_GUARD = 8
HOME_MAJOR_TICKERS = [
    "005930.KS", "000660.KS", "NVDA", "AAPL",
    "MSFT", "META", "TSLA", "GOOGL",
]
HOME_SNAPSHOT_LOCK = asyncio.Lock()

app = FastAPI(title="주식 비교 차트", version="1.0.0")

# CORS 설정 - 토스 앱인토스 도메인 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chartview.apps.tossmini.com",        # 실제 서비스 환경
        "https://chartview.private-apps.tossmini.com", # 콘솔 QR 테스트 환경
        "https://chart-view-bsg6.onrender.com",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
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
    return {"status": "ok", "timestamp": datetime.now().isoformat(),
            "revision": os.environ.get("RENDER_GIT_COMMIT", "local")}

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
    """Start keep-alive and warm the shared Home snapshot before traffic arrives."""
    ping_thread = threading.Thread(target=self_ping_worker, daemon=True)
    ping_thread.start()
    try:
        _seed_home_snapshot_from_disk()
        await asyncio.wait_for(_refresh_home_snapshot(force=True), timeout=12)
        try:
            await asyncio.wait_for(_refresh_market_now(force=True), timeout=10)
            print("[MARKET NOW] shared snapshot warmed")
        except Exception as market_exc:
            print(f"[MARKET NOW] warmup deferred: {market_exc}")
        print("[HOME] shared snapshot warmed")
    except Exception as exc:
        # The disk seed still lets Home render immediately even if Yahoo is temporarily slow.
        print(f"[HOME] warmup deferred: {exc}")


@app.get("/")
async def home(request: Request):
    response = templates.TemplateResponse("index.html", {"request": request})
    # Always fetch the current HTML shell; versioned static assets remain cacheable.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.head("/")
async def home_head():
    return JSONResponse(content={}, status_code=200)


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
        # local-screener-universe-v4: GitHub Actions가 만든 전체 종목 JSON을 먼저 사용.
        # Render cold start에서 KIND를 다시 다운로드하던 수초 지연을 제거한다.
        try:
            import json as _json
            local_path = os.path.join(os.path.dirname(__file__), "static", "data", "screener.json")
            with open(local_path, "r", encoding="utf-8") as f:
                payload = _json.load(f)
            local_rows = []
            for row in payload.get("stocks", []):
                code = str(row.get("code") or "").zfill(6)
                name = str(row.get("name") or "").strip()
                market = str(row.get("market") or "")
                if code and name and market in ("KOSPI", "KOSDAQ"):
                    local_rows.append({
                        "code": code, "name": name, "market": market,
                        "suffix": ".KS" if market == "KOSPI" else ".KQ"
                    })
            if local_rows:
                KRX_STOCK_LIST = local_rows
                KRX_CACHE_TIME = time.time()
                return KRX_STOCK_LIST
        except Exception as e:
            print(f"[KRX] Local screener universe unavailable: {e}")

        # Fallback: KIND bulk download
        headers = {"User-Agent": "Mozilla/5.0"}
        all_stocks = []
        
        # KOSPI / KOSDAQ 시장 정보를 함께 저장해 Yahoo suffix를 정확히 결정
        markets = [("stockMkt", "KOSPI", ".KS"), ("kosdaqMkt", "KOSDAQ", ".KQ")]
        for market_type, market_name, suffix in markets:
            url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
            params = {"method": "download", "marketType": market_type}
            try:
                res = requests.get(url, params=params, headers=headers, timeout=10)
                df = pd.read_html(io.StringIO(res.text))[0]
                for _, row in df.iterrows():
                    code = str(row["종목코드"]).zfill(6)
                    name = str(row["회사명"]).strip()
                    all_stocks.append({"code": code, "name": name, "market": market_name, "suffix": suffix})
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
def search_stocks(q: str = Query(max_length=100)):
    """Unified fast search: local KRX universe + local aliases, no yfinance.info."""
    query = (q or "").strip()
    if not query:
        return {"results": []}

    aliases = {
        "삼전": "삼성전자", "하닉": "SK하이닉스", "삼바": "삼성바이오로직스",
        "엘전": "LG전자", "현차": "현대차", "네이버": "NAVER",
    }
    lookup = aliases.get(query.lower(), query)
    ql = query.lower()
    ll = lookup.lower()
    found = {}

    def put(symbol, name, kind="GLOBAL", code=None, market=None, score=50):
        old = found.get(symbol)
        row = {"symbol": symbol, "name": name, "type": kind, "score": score}
        if code: row["code"] = code
        if market: row["market"] = market
        if old is None or score < old["score"]:
            found[symbol] = row

    # Small hand-curated alias DB is instant and also resolves Korean names such as 애플/테슬라.
    for stock in STOCK_DATABASE:
        symbol = stock["symbol"]
        name = stock["name"]
        blob = f"{symbol} {name} {stock.get('keywords', '')}".lower()
        if ql == symbol.lower() or ql == name.lower() or ll == symbol.lower() or ll == name.lower():
            put(symbol, name, "LOCAL", score=0)
        elif name.lower().startswith(ql) or symbol.lower().startswith(ql):
            put(symbol, name, "LOCAL", score=1)
        elif ql in blob or ll in blob:
            put(symbol, name, "LOCAL", score=3)

    # Full KRX lookup is read from local screener.json; no network on normal operation.
    has_korean = any('가' <= c <= '힣' for c in lookup)
    is_code = lookup.isdigit() and len(lookup) == 6
    if has_korean or is_code or query.isascii():
        for stock in load_krx_stock_list():
            name = stock["name"]
            code = stock["code"]
            if (is_code and code == lookup) or ll in name.lower():
                score = 0 if (name == lookup or code == lookup) else (1 if name.startswith(lookup) else 2)
                put(f"{code}{stock.get('suffix', '.KS')}", name, "KRX", code, stock.get("market"), score)

    results = sorted(found.values(), key=lambda x: (x["score"], x["name"]))[:10]
    for row in results:
        row.pop("score", None)

    # Unknown ASCII ticker: add immediately and let /api/compare validate it.
    if not results and re.fullmatch(r"[A-Za-z^][A-Za-z0-9.^=\-]{0,19}", lookup) and not is_code:
        results = [{"symbol": lookup.upper(), "name": lookup.upper(), "type": "DIRECT"}]

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


def validated_tickers(raw: str) -> list[str]:
    symbols = list(dict.fromkeys(t.strip().upper() for t in raw.split(",") if t.strip()))
    if not symbols or len(symbols) > 6:
        raise HTTPException(400, "종목은 1개 이상 6개 이하로 입력해주세요.")
    if any(not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,19}", t) for t in symbols):
        raise HTTPException(400, "유효한 종목코드 또는 티커를 입력해주세요.")
    return symbols


@app.get("/api/compare")
async def compare_stocks(tickers: str, period: str = "1mo", start: str = None, end: str = None):
    ticker_list = validated_tickers(tickers)
    if period not in {"1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max"}:
        raise HTTPException(400, "지원하지 않는 조회 기간입니다.")
    if bool(start) != bool(end):
        raise HTTPException(400, "시작일과 종료일을 함께 입력해주세요.")
    if start and end:
        try:
            first, last = [datetime.strptime(value, "%Y-%m-%d") for value in (start, end)]
            if first > last:
                raise ValueError("reversed range")
        except ValueError:
            raise HTTPException(400, "조회 날짜와 시작일·종료일 순서를 확인해주세요.")
    fetched = await asyncio.gather(*[asyncio.to_thread(fetch_compare_stock, t, period, start, end) for t in ticker_list], return_exceptions=True)
    by_ticker, errors = {}, []
    for ticker, item in zip(ticker_list, fetched):
        if isinstance(item, Exception): errors.append({"ticker": ticker, "message": str(item)})
        elif item: by_ticker[ticker] = item
        else: errors.append({"ticker": ticker, "message": "시세 데이터를 가져오지 못했습니다."})
    return {"stocks": [by_ticker[t] for t in ticker_list if t in by_ticker], "errors": errors,
  "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "source": "Yahoo Finance Chart"}


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



MARKET_NOW_TICKERS = ["^KS11", "^KQ11", "^GSPC", "^IXIC", "^TNX", "^VIX", "CL=F", "KRW=X"]
MARKET_NOW_CACHE = {"data": None, "timestamp": 0.0, "refreshing": False}
MARKET_NOW_TTL = 60
MARKET_NOW_REFRESH_GUARD = 8
MARKET_NOW_LOCK = asyncio.Lock()


async def _refresh_market_now(force: bool = False):
    """Refresh one shared market snapshot while keeping the last successful rows available."""
    now = time.time()
    cached = MARKET_NOW_CACHE.get("data")
    if cached and not force and now - MARKET_NOW_CACHE.get("timestamp", 0) < MARKET_NOW_REFRESH_GUARD:
        return cached

    async with MARKET_NOW_LOCK:
        now = time.time()
        cached = MARKET_NOW_CACHE.get("data")
        if cached and not force and now - MARKET_NOW_CACHE.get("timestamp", 0) < MARKET_NOW_REFRESH_GUARD:
            return cached

        MARKET_NOW_CACHE["refreshing"] = True
        try:
            previous = {
                row.get("ticker"): row
                for row in ((cached or {}).get("results") or [])
                if isinstance(row, dict) and row.get("ticker")
            }
            fetched = await asyncio.gather(
                *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in MARKET_NOW_TICKERS],
                return_exceptions=True,
            )
            results, errors = [], []
            for ticker, row in zip(MARKET_NOW_TICKERS, fetched):
                if isinstance(row, Exception) or not row:
                    old = previous.get(ticker)
                    if old:
                        results.append({**old, "stale": True})
                    errors.append({"ticker": ticker, "message": str(row) if isinstance(row, Exception) else "시세 데이터를 가져오지 못했습니다."})
                    continue
                results.append({
                    "ticker": ticker,
                    "name": row.get("name") or ticker,
                    "price": row.get("price"),
                    "change": row.get("change"),
                    "currency": row.get("currency"),
                    "asOf": row.get("asOf"),
                    "stale": False,
                    "source": row.get("source") or "Yahoo Chart",
                })

            if not results and cached:
                return cached

            now_kst = datetime.utcnow() + timedelta(hours=9)
            data = {
                "results": results,
                "errors": errors,
                "timestamp": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "date": now_kst.strftime("%Y-%m-%d"),
                "basis": "previous_close",
                "source": "Yahoo Finance Chart",
            }
            MARKET_NOW_CACHE["data"] = data
            MARKET_NOW_CACHE["timestamp"] = time.time()
            return data
        finally:
            MARKET_NOW_CACHE["refreshing"] = False


@app.get("/api/market-now")
async def market_now(fresh: bool = False):
    """Return shared market cache immediately; revalidate stale data in the background."""
    data = MARKET_NOW_CACHE.get("data")
    if fresh:
        try:
            data = await _refresh_market_now(force=True) or data
        except Exception as exc:
            print(f"[MARKET NOW] foreground refresh failed: {exc}")
    elif not data:
        try:
            data = await _refresh_market_now(force=True)
        except Exception as exc:
            print(f"[MARKET NOW] first refresh failed: {exc}")
    else:
        age = time.time() - MARKET_NOW_CACHE.get("timestamp", 0)
        if age >= MARKET_NOW_TTL and not MARKET_NOW_CACHE.get("refreshing"):
            asyncio.create_task(_refresh_market_now(force=False))

    payload = dict(data or {"results": [], "errors": []})
    payload["cacheAgeSec"] = round(max(0.0, time.time() - MARKET_NOW_CACHE.get("timestamp", 0)), 1)
    payload["refreshing"] = bool(MARKET_NOW_CACHE.get("refreshing"))
    payload["cacheMode"] = "stale-while-revalidate"
    return payload

@app.get("/api/heatmap")
async def heatmap_data():
    """Heatmap snapshots via the lightweight chart endpoint (no yfinance.info)."""
    heatmap_tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
        "JPM", "V", "MA", "UNH", "JNJ", "LLY", "XOM", "AVGO",
        "005930.KS", "000660.KS", "035420.KS", "035720.KS", "005380.KS"
    ]
    fetched = await asyncio.gather(
        *[asyncio.to_thread(fetch_quote_snapshot, t) for t in heatmap_tickers],
        return_exceptions=True,
    )
    results = []
    for ticker, row in zip(heatmap_tickers, fetched):
        if isinstance(row, Exception) or not row:
            continue
        results.append({
            "ticker": ticker,
            "name": row.get("name") or ticker,
            "change": row.get("change", 0),
            "price": row.get("price"),
            "marketCap": row.get("marketCap") or 0,
        })
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
    """Serve precomputed FRED/Yahoo macro data from the committed cache.

    Render never calls FRED here. GitHub Actions refreshes
    static/data/macro_cache.json on a schedule, avoiding shared-IP
    timeouts and keeping this endpoint fast and deterministic.
    """
    global MACRO_CACHE
    current_time = time.time()

    # Short in-process cache avoids repeated JSON parsing while still
    # allowing a newly deployed cache file to be picked up quickly.
    if MACRO_CACHE["data"] and (current_time - MACRO_CACHE["timestamp"] < 300):
        return MACRO_CACHE["data"]

    cache_path = os.path.join(os.path.dirname(__file__), "static", "data", "macro_cache.json")
    try:
        import json as _json
        with open(cache_path, "r", encoding="utf-8") as f:
            payload = _json.load(f)
    except Exception as exc:
        print(f"[MACRO] cache unavailable: {exc}")
        if MACRO_CACHE["data"]:
            return MACRO_CACHE["data"]
        return JSONResponse(
            {"results": [], "error": "경제지표 캐시를 불러오지 못했습니다.", "cacheMode": "precomputed"},
            status_code=503,
        )

    ordered = [
        row for row in (payload.get("results") or [])
        if isinstance(row, dict) and row.get("chart_data")
    ]
    if len(ordered) < 8:
        print(f"[MACRO] cache incomplete: {len(ordered)} rows")
        if MACRO_CACHE["data"]:
            return MACRO_CACHE["data"]

    net_liquidity = compute_net_liquidity(ordered)
    summary = generate_macro_summary(ordered, net_liquidity)
    basis_dates = sorted(str(row.get("asOf"))[:10] for row in ordered if row.get("asOf"))
    if isinstance(summary, dict):
        summary = {**summary,
                   "latestBasisDate": basis_dates[-1] if basis_dates else None,
                   "oldestBasisDate": basis_dates[0] if basis_dates else None}
    response_data = {
        "results": ordered,
        "net_liquidity": net_liquidity,
        "summary": summary,
        "generatedAt": payload.get("generatedAt"),
        "freshCount": payload.get("freshCount", len(ordered)),
        "staleCount": payload.get("staleCount", 0),
        "staleSymbols": payload.get("staleSymbols", []),
        "errors": payload.get("errors", {}),
        "source": payload.get("source", "FRED + Yahoo Chart, precomputed by GitHub Actions"),
        "cacheMode": "precomputed",
        "basis": {
            "latest": basis_dates[-1] if basis_dates else None,
            "oldest": basis_dates[0] if basis_dates else None,
            "meaning": "source observation dates; collection time is generatedAt",
        },
    }
    MACRO_CACHE["data"] = response_data
    MACRO_CACHE["timestamp"] = current_time
    print(
        f"[MACRO] served {len(ordered)} cached indicators "
        f"(fresh={response_data['freshCount']}, stale={response_data['staleCount']})"
    )
    return response_data


def _seed_home_snapshot_from_disk():
    """Best-effort cold-start seed from the committed daily valuation cache."""
    if HOME_SNAPSHOT_CACHE.get("data"):
        return HOME_SNAPSHOT_CACHE["data"]
    results = []
    try:
        import json as _json
        cache_path = os.path.join(os.path.dirname(__file__), "static", "data", "valuation_cache.json")
        with open(cache_path, "r", encoding="utf-8") as f:
            disk_payload = _json.load(f)
            quotes = disk_payload.get("quotes") or {}
        for ticker in HOME_MAJOR_TICKERS:
            row = quotes.get(ticker) or {}
            price = row.get("regularMarketPrice")
            if price is None:
                price = row.get("price")
            change = row.get("regularMarketChangePercent")
            if change is None:
                change = row.get("change")
            if price is None:
                continue
            results.append({
                "ticker": ticker,
                "name": row.get("shortName") or ticker,
                "price": price,
                "change": change,
                "marketCap": row.get("marketCap") or 0,
                "asOf": disk_payload.get("generatedAt"),
                "stale": True,
            })
    except Exception as exc:
        print(f"[HOME] disk seed unavailable: {exc}")

    if results:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        HOME_SNAPSHOT_CACHE["data"] = {
            "heatmap": {"results": results},
            "macro": MACRO_CACHE.get("data"),
            "generatedAt": disk_payload.get("generatedAt"),
            "source": "disk-seed",
        }
        HOME_SNAPSHOT_CACHE["timestamp"] = time.time()
    return HOME_SNAPSHOT_CACHE.get("data")


async def _refresh_home_snapshot(force: bool = False):
    """Refresh the shared snapshot once, preserving old rows when a provider is partial."""
    now = time.time()
    cached = HOME_SNAPSHOT_CACHE.get("data")
    if cached and not force and now - HOME_SNAPSHOT_CACHE.get("timestamp", 0) < HOME_SNAPSHOT_REFRESH_GUARD:
        return cached

    async with HOME_SNAPSHOT_LOCK:
        now = time.time()
        cached = HOME_SNAPSHOT_CACHE.get("data")
        if cached and not force and now - HOME_SNAPSHOT_CACHE.get("timestamp", 0) < HOME_SNAPSHOT_REFRESH_GUARD:
            return cached

        HOME_SNAPSHOT_CACHE["refreshing"] = True
        try:
            previous_rows = {
                row.get("ticker"): row
                for row in ((cached or {}).get("heatmap", {}).get("results") or [])
                if isinstance(row, dict) and row.get("ticker")
            }
            fetched = await asyncio.gather(
                *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in HOME_MAJOR_TICKERS],
                return_exceptions=True,
            )
            results = []
            for ticker, row in zip(HOME_MAJOR_TICKERS, fetched):
                if isinstance(row, Exception) or not row:
                    old = previous_rows.get(ticker)
                    if old:
                        results.append({**old, "stale": True})
                    continue
                results.append({
                    "ticker": ticker,
                    "name": row.get("name") or ticker,
                    "change": row.get("change"),
                    "price": row.get("price"),
                    "marketCap": row.get("marketCap") or 0,
                    "asOf": row.get("asOf"),
                    "stale": False,
                })

            if not results and cached:
                return cached

            macro_payload = None
            try:
                macro_candidate = await macro_data()
                if not isinstance(macro_candidate, JSONResponse):
                    macro_payload = macro_candidate
            except Exception as exc:
                print(f"[HOME] macro snapshot refresh failed: {exc}")
            if macro_payload is None and cached:
                macro_payload = cached.get("macro")

            now_kst = datetime.utcnow() + timedelta(hours=9)
            data = {
                "heatmap": {"results": results},
                "macro": macro_payload,
                "generatedAt": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "shared-memory-swr",
            }
            HOME_SNAPSHOT_CACHE["data"] = data
            HOME_SNAPSHOT_CACHE["timestamp"] = time.time()
            return data
        finally:
            HOME_SNAPSHOT_CACHE["refreshing"] = False


@app.get("/api/home-snapshot")
async def home_snapshot(fresh: bool = False):
    """Return the last successful Home snapshot immediately and revalidate behind it."""
    data = HOME_SNAPSHOT_CACHE.get("data") or _seed_home_snapshot_from_disk()
    if fresh:
        try:
            data = await _refresh_home_snapshot(force=True) or data
        except Exception as exc:
            print(f"[HOME] foreground refresh failed: {exc}")
    elif not data:
        try:
            data = await _refresh_home_snapshot(force=True)
        except Exception as exc:
            print(f"[HOME] first refresh failed: {exc}")
    else:
        age = time.time() - HOME_SNAPSHOT_CACHE.get("timestamp", 0)
        if age >= HOME_SNAPSHOT_TTL and not HOME_SNAPSHOT_CACHE.get("refreshing"):
            asyncio.create_task(_refresh_home_snapshot(force=False))

    payload = dict(data or {"heatmap": {"results": []}, "macro": None})
    payload["cacheAgeSec"] = round(max(0.0, time.time() - HOME_SNAPSHOT_CACHE.get("timestamp", 0)), 1)
    payload["refreshing"] = bool(HOME_SNAPSHOT_CACHE.get("refreshing"))
    payload["cacheMode"] = "stale-while-revalidate"
    return payload


@app.get("/api/fwd-per")
@app.get("/api/valuation")
async def valuation_data(tickers: str):
    ticker_list = validated_tickers(tickers)
    fetched = await asyncio.gather(*[asyncio.to_thread(fetch_valuation_snapshot, t) for t in ticker_list], return_exceptions=True)
    stocks, errors = [], []
    for ticker, item in zip(ticker_list, fetched):
        if isinstance(item, Exception): errors.append({"ticker": ticker, "message": str(item)})
        elif item: stocks.append(item)
        else: errors.append({"ticker": ticker, "message": "밸류에이션 데이터를 가져오지 못했습니다."})
    return {"stocks": stocks, "errors": errors, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  "source": "Yahoo Finance Chart + Fundamentals"}


@app.get("/api/valuation-band")
async def valuation_band_data(ticker: str, years: int = Query(default=3, ge=1, le=10)):
    symbol = validated_tickers(ticker)[0]
    try:
        data = await asyncio.to_thread(fetch_valuation_bands, symbol, years)
        return data
    except Exception as exc:
        print(f"[ValuationBand] {symbol} failed: {exc}")
        return JSONResponse(
            {"error": "역사적 밸류에이션 데이터를 계산하지 못했습니다.", "ticker": symbol},
            status_code=503,
        )


@app.get("/api/consensus")
async def consensus_data(ticker: str):
    symbol = validated_tickers(ticker)[0]
    try:
        return await asyncio.to_thread(fetch_consensus, symbol)
    except Exception as exc:
        print(f"[Consensus] {symbol} failed: {exc}")
        return JSONResponse(
            {"error": "애널리스트 컨센서스 데이터를 불러오지 못했습니다.", "ticker": symbol},
            status_code=503,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
