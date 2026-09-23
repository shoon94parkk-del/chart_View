"""
토스 미니앱 - 주식 비교 차트
FastAPI 서버 (토스 가이드라인 준수)
"""

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import io
import time
import base64
import asyncio
import os
import threading
import re
import hashlib
import secrets
import json
try:
    import redis.asyncio as redis_async
except Exception:
    redis_async = None
import market_service as _market_service
from realtime_korea import install_patch as _install_korea_realtime

# Bind the canonical Korean realtime path before local function aliases are made.
_install_korea_realtime(_market_service)
fetch_compare_stock = _market_service.fetch_compare_stock
fetch_valuation_snapshot = _market_service.fetch_valuation_snapshot
fetch_quote_snapshot = _market_service.fetch_quote_snapshot
fetch_history_series = _market_service.fetch_history_series
from valuation_band_service import fetch_valuation_bands
from consensus_service import fetch_consensus
from news_service_v37 import router as news_router_v37
from news_summary_service import router as news_summary_router_v43
from profile_sync_service import router as profile_sync_router

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
    "005930.KS", "000660.KS", "207940.KS", "005380.KS",
    "000270.KS", "373220.KS", "035420.KS", "068270.KS",
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN",
    "TSM", "META", "AVGO", "TSLA", "AMD",
]
HOME_SNAPSHOT_LOCK = asyncio.Lock()

HOME_LIVE_ACTIVE_REFRESH_SEC = 5.0
HOME_LIVE_CLOSED_REFRESH_SEC = 300.0
HOME_LIVE_IDLE_CHECK_SEC = 30.0
VISITOR_HEARTBEAT_SEC = 20
VISITOR_ACTIVE_WINDOW_SEC = 45
HOME_LIVE_CACHE = {
    "quotes": {},
    "updatedAt": None,
    "marketUpdatedAt": {"KR": None, "US": None},
    "marketUpdatedEpoch": {"KR": 0.0, "US": 0.0},
    "refreshing": False,
    "lastError": None,
    "source": "render-memory-v66",
}
HOME_LIVE_REFRESH_LOCK = asyncio.Lock()
HOME_LIVE_WAKE_EVENT = None
VISITOR_STATE_LOCK = threading.Lock()
VISITOR_LAST_SEEN = {}
VISITOR_DAILY = {}
ANALYTICS_REDIS_CLIENT = None
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()
KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


# P0-2: Home support data is immutable for a running Render revision.
# Keep parsed source files in memory so each Home request does not re-read/re-parse
# the full Korean screener JSON.
HOME_INSIGHTS_SOURCE_CACHE = {"data": None, "timestamp": 0.0}
HOME_INSIGHTS_SOURCE_TTL = 300

app = FastAPI(title="주식 비교 차트", version="1.0.0")

# V37 personalized watchlist news router.
app.include_router(news_router_v37)
app.include_router(news_summary_router_v43)
app.include_router(profile_sync_router)

# CORS 설정 - 토스 앱인토스 도메인 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chartview.web.tossmini.com",         # SDK 3.x production
        "https://chartview.private-web.tossmini.com", # SDK 3.x QR preview
        "https://chartview.apps.tossmini.com",        # 실제 서비스 환경
        "https://chartview.private-apps.tossmini.com", # 콘솔 QR 테스트 환경
        "https://chart-view-toss.onrender.com",       # Render Toss preview
        "https://chart-view-pkv8.onrender.com",       # current Chart View production
        "https://chart-view-bsg6.onrender.com",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)


@app.middleware("http")
async def cache_static_assets(request: Request, call_next):
    """Cache versioned code immutably while keeping mutable data refreshable."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        if request.url.path.startswith("/static/data/"):
            response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=86400"
        elif request.query_params.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return response

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


def _market_is_open(local_dt: datetime, start_hour: int, start_minute: int, end_hour: int, end_minute: int) -> bool:
    if local_dt.weekday() >= 5:
        return False
    minute = local_dt.hour * 60 + local_dt.minute
    return start_hour * 60 + start_minute <= minute < end_hour * 60 + end_minute


def _open_home_markets(now_utc: datetime | None = None) -> dict[str, list[str]]:
    now_utc = now_utc or datetime.now(timezone.utc)
    markets = {}
    kr = now_utc.astimezone(KST)
    us = now_utc.astimezone(ET)
    if _market_is_open(kr, 9, 0, 15, 30):
        markets["KR"] = [ticker for ticker in HOME_MAJOR_TICKERS if ticker.endswith((".KS", ".KQ"))]
    if _market_is_open(us, 9, 30, 16, 0):
        markets["US"] = [ticker for ticker in HOME_MAJOR_TICKERS if not ticker.endswith((".KS", ".KQ"))]
    return markets


def _all_home_markets() -> dict[str, list[str]]:
    """All Home quote groups, including closed markets.

    Closed markets still need periodic refreshes so the final regular-session
    close replaces any older disk/local cache after the bell or a deploy.
    """
    return {
        "KR": [ticker for ticker in HOME_MAJOR_TICKERS if ticker.endswith((".KS", ".KQ"))],
        "US": [ticker for ticker in HOME_MAJOR_TICKERS if not ticker.endswith((".KS", ".KQ"))],
    }


def _today_kst() -> str:
    return datetime.now(timezone.utc).astimezone(KST).date().isoformat()


def _visitor_hash(visitor_id: str, day: str) -> str:
    salt = os.environ.get("CHARTVIEW_ANALYTICS_SALT") or os.environ.get("CHARTVIEW_ADMIN_TOKEN") or "chartview-local"
    return hashlib.sha256(f"{salt}:{day}:{visitor_id}".encode("utf-8")).hexdigest()


def _record_visitor(visitor_id: str, surface: str) -> tuple[int, int]:
    now = time.time()
    day = _today_kst()
    visitor_key = _visitor_hash(visitor_id, day)
    surface = surface if surface in {"home", "watchlist", "chart", "market", "screener", "pick", "other"} else "other"
    with VISITOR_STATE_LOCK:
        VISITOR_DAILY.setdefault(day, set()).add(visitor_key)
        VISITOR_LAST_SEEN[visitor_key] = {"timestamp": now, "surface": surface}
        for old_day in list(VISITOR_DAILY):
            try:
                if (datetime.fromisoformat(day).date() - datetime.fromisoformat(old_day).date()).days > 7:
                    VISITOR_DAILY.pop(old_day, None)
            except Exception:
                VISITOR_DAILY.pop(old_day, None)
        stale_cutoff = now - 86400
        for key, row in list(VISITOR_LAST_SEEN.items()):
            if float(row.get("timestamp") or 0) < stale_cutoff:
                VISITOR_LAST_SEEN.pop(key, None)
        active = [row for row in VISITOR_LAST_SEEN.values() if now - float(row.get("timestamp") or 0) <= VISITOR_ACTIVE_WINDOW_SEC]
        return len(active), sum(1 for row in active if row.get("surface") == "home")


def _visitor_counts() -> tuple[int, int, int]:
    now = time.time()
    day = _today_kst()
    with VISITOR_STATE_LOCK:
        active = [row for row in VISITOR_LAST_SEEN.values() if now - float(row.get("timestamp") or 0) <= VISITOR_ACTIVE_WINDOW_SEC]
        return (
            len(VISITOR_DAILY.get(day, set())),
            len(active),
            sum(1 for row in active if row.get("surface") == "home"),
        )


async def _analytics_redis_client():
    global ANALYTICS_REDIS_CLIENT
    if ANALYTICS_REDIS_CLIENT is not None:
        return ANALYTICS_REDIS_CLIENT
    url = os.environ.get("CHARTVIEW_ANALYTICS_REDIS") or ""
    if not url or redis_async is None:
        return None
    try:
        client = redis_async.from_url(url, decode_responses=True, socket_timeout=1.5)
        await client.ping()
        ANALYTICS_REDIS_CLIENT = client
        print('[ANALYTICS] Render Key Value connected')
        return client
    except Exception as exc:
        print(f"[ANALYTICS] Redis unavailable, memory fallback: {exc}")
        return None


async def _persist_daily_visitor(visitor_id: str) -> bool:
    client = await _analytics_redis_client()
    if client is None:
        return False
    day = _today_kst()
    key = f"chartview:visitors:{day}"
    try:
        await client.sadd(key, _visitor_hash(visitor_id, day))
        await client.expire(key, 60 * 60 * 24 * 10)
        return True
    except Exception as exc:
        print(f"[ANALYTICS] Redis write failed: {exc}")
        return False


async def _persistent_today_unique() -> tuple[int | None, str]:
    client = await _analytics_redis_client()
    if client is None:
        return None, "memory"
    key = f"chartview:visitors:{_today_kst()}"
    try:
        return int(await client.scard(key)), "render-key-value"
    except Exception as exc:
        print(f"[ANALYTICS] Redis read failed: {exc}")
        return None, "memory"


def _seed_home_live_from_snapshot(snapshot: dict | None) -> None:
    if not snapshot:
        return
    quotes = HOME_LIVE_CACHE["quotes"]
    for row in ((snapshot.get("heatmap") or {}).get("results") or []):
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in HOME_MAJOR_TICKERS:
            continue
        quotes[ticker] = {
            "ticker": ticker,
            "price": row.get("price"),
            "change": row.get("change"),
            "asOf": row.get("asOf"),
            "currency": "KRW" if ticker.endswith((".KS", ".KQ")) else "USD",
            "source": "home snapshot fallback",
            "marketStatus": None,
            "delayTime": None,
        }


def _home_live_results() -> list[dict]:
    quotes = HOME_LIVE_CACHE.get("quotes") or {}
    return [dict(quotes[ticker]) for ticker in HOME_MAJOR_TICKERS if ticker in quotes]


async def _refresh_home_live(markets: dict[str, list[str]]) -> None:
    if not markets:
        return
    async with HOME_LIVE_REFRESH_LOCK:
        HOME_LIVE_CACHE["refreshing"] = True
        try:
            symbols = []
            market_by_symbol = {}
            for market, tickers in markets.items():
                for ticker in tickers:
                    symbols.append(ticker)
                    market_by_symbol[ticker] = market
            fetched = await asyncio.gather(
                *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in symbols],
                return_exceptions=True,
            )
            now_epoch = time.time()
            now_iso = datetime.now(timezone.utc).isoformat()
            good_markets = set()
            errors = []
            for ticker, item in zip(symbols, fetched):
                if isinstance(item, Exception):
                    errors.append(f"{ticker}: {item}")
                    continue
                if not item:
                    errors.append(f"{ticker}: empty quote")
                    continue
                HOME_LIVE_CACHE["quotes"][ticker] = item
                good_markets.add(market_by_symbol[ticker])

            if good_markets:
                HOME_LIVE_CACHE["updatedAt"] = now_iso
                for market in good_markets:
                    HOME_LIVE_CACHE["marketUpdatedAt"][market] = now_iso
                    HOME_LIVE_CACHE["marketUpdatedEpoch"][market] = now_epoch
            HOME_LIVE_CACHE["lastError"] = "; ".join(errors[:4]) if errors else None
            if "US" in markets and "US" not in _open_home_markets():
                audit_symbols = {"META", "AMD", "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSM", "AVGO", "TSLA"}
                audit = {
                    ticker: {
                        "price": HOME_LIVE_CACHE["quotes"].get(ticker, {}).get("price"),
                        "previousClose": HOME_LIVE_CACHE["quotes"].get(ticker, {}).get("previousClose"),
                        "change": HOME_LIVE_CACHE["quotes"].get(ticker, {}).get("change"),
                        "sessionDate": HOME_LIVE_CACHE["quotes"].get(ticker, {}).get("sessionDate"),
                        "previousSessionDate": HOME_LIVE_CACHE["quotes"].get(ticker, {}).get("previousSessionDate"),
                        "asOf": HOME_LIVE_CACHE["quotes"].get(ticker, {}).get("asOf"),
                    }
                    for ticker in audit_symbols
                    if ticker in HOME_LIVE_CACHE["quotes"]
                }
                if audit:
                    print("[HOME_AUDIT] " + json.dumps(audit, ensure_ascii=False, sort_keys=True))
        finally:
            HOME_LIVE_CACHE["refreshing"] = False


async def _home_live_worker() -> None:
    global HOME_LIVE_WAKE_EVENT
    if HOME_LIVE_WAKE_EVENT is None:
        HOME_LIVE_WAKE_EVENT = asyncio.Event()
    all_markets = _all_home_markets()
    while True:
        open_markets = _open_home_markets()
        _, _, active_home = _visitor_counts()
        timeout = HOME_LIVE_IDLE_CHECK_SEC

        if active_home > 0:
            now = time.time()
            due = {}
            wait_for = HOME_LIVE_CLOSED_REFRESH_SEC
            for market, tickers in all_markets.items():
                interval = HOME_LIVE_ACTIVE_REFRESH_SEC if market in open_markets else HOME_LIVE_CLOSED_REFRESH_SEC
                age = now - float(HOME_LIVE_CACHE["marketUpdatedEpoch"].get(market) or 0)
                if age >= interval:
                    due[market] = tickers
                else:
                    wait_for = min(wait_for, max(0.5, interval - age))
            if due:
                await _refresh_home_live(due)
                wait_for = HOME_LIVE_ACTIVE_REFRESH_SEC if open_markets else HOME_LIVE_CLOSED_REFRESH_SEC
            timeout = wait_for

        try:
            await asyncio.wait_for(HOME_LIVE_WAKE_EVENT.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            HOME_LIVE_WAKE_EVENT.clear()


def _admin_token_ok(request: Request) -> bool:
    expected = os.environ.get("CHARTVIEW_ADMIN_TOKEN") or ""
    supplied = request.headers.get("X-ChartView-Admin") or ""
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


@app.on_event("startup")
async def startup_event():
    """Serve cached data immediately and keep live Home quotes warm only for active Home visitors."""
    global HOME_LIVE_WAKE_EVENT
    ping_thread = threading.Thread(target=self_ping_worker, daemon=True)
    ping_thread.start()
    snapshot = _seed_home_snapshot_from_disk()
    _seed_home_live_from_snapshot(snapshot)
    HOME_LIVE_WAKE_EVENT = asyncio.Event()
    asyncio.create_task(_home_live_worker())
    # Replace disk-seeded quotes immediately, even while KR/US markets are closed.
    asyncio.create_task(_refresh_home_live(_all_home_markets()))
    asyncio.create_task(_analytics_redis_client())
    asyncio.create_task(_refresh_home_snapshot(force=True))
    asyncio.create_task(_refresh_market_now(force=True))


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



@app.post("/api/activity")
async def visitor_activity(request: Request):
    """Privacy-light heartbeat used for anonymous daily browser counts and adaptive Home polling."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    visitor_id = str(body.get("visitorId") or "").strip()
    surface = str(body.get("surface") or "other").strip().lower()
    if not visitor_id or len(visitor_id) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", visitor_id):
        raise HTTPException(400, "유효한 방문자 식별자가 필요합니다.")
    _record_visitor(visitor_id, surface)
    await _persist_daily_visitor(visitor_id)
    if HOME_LIVE_WAKE_EVENT is not None and surface == "home":
        HOME_LIVE_WAKE_EVENT.set()
    return {
        "ok": True,
        "heartbeatSec": VISITOR_HEARTBEAT_SEC,
    }


@app.get("/api/home-live")
async def home_live_snapshot():
    """Return the shared Home quote snapshot, warming it once if only disk data exists."""
    if not HOME_LIVE_CACHE.get("updatedAt"):
        await _refresh_home_live(_all_home_markets())
    updated = HOME_LIVE_CACHE.get("updatedAt")
    age = None
    if updated:
        try:
            age = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds())
        except Exception:
            age = None
    return {
        "results": _home_live_results(),
        "updatedAt": updated,
        "marketUpdatedAt": dict(HOME_LIVE_CACHE.get("marketUpdatedAt") or {}),
        "cacheAgeSec": round(age, 2) if age is not None else None,
        "refreshing": bool(HOME_LIVE_CACHE.get("refreshing")),
        "source": "Render shared memory · server-driven V66",
    }


@app.get("/admin/usage")
async def admin_usage_page(request: Request):
    response = templates.TemplateResponse("admin_usage.html", {"request": request})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/api/admin/usage")
async def admin_usage_data(request: Request):
    if not _admin_token_ok(request):
        raise HTTPException(403, "관리자 인증이 필요합니다.")
    memory_today, active_now, active_home = _visitor_counts()
    persistent_today, backend = await _persistent_today_unique()
    markets = _open_home_markets()
    payload = {
        "date": _today_kst(),
        "todayUniqueBrowsers": persistent_today if persistent_today is not None else memory_today,
        "activeNow": active_now,
        "activeHome": active_home,
        "heartbeatWindowSec": VISITOR_ACTIVE_WINDOW_SEC,
        "serverStartedAt": SERVER_STARTED_AT,
        "countScope": (
            "anonymous browser ID · daily unique in Render Key Value"
            if backend == "render-key-value"
            else "anonymous browser ID · current Render process memory fallback"
        ),
        "analyticsBackend": backend,
        "live": {
            "openMarkets": list(markets),
            "updatedAt": HOME_LIVE_CACHE.get("updatedAt"),
            "marketUpdatedAt": dict(HOME_LIVE_CACHE.get("marketUpdatedAt") or {}),
            "rows": len(HOME_LIVE_CACHE.get("quotes") or {}),
            "refreshing": bool(HOME_LIVE_CACHE.get("refreshing")),
            "lastError": HOME_LIVE_CACHE.get("lastError"),
            "mode": "5s while Home has active visitors; no provider polling when Home is idle/markets closed",
        },
    }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/quotes")
async def quote_snapshots(tickers: str):
    symbols = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
    if not symbols or len(symbols) > 20:
        raise HTTPException(400, "종목은 1개 이상 20개 이하로 입력해주세요.")
    if any(not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,19}", t) for t in symbols):
        raise HTTPException(400, "유효한 종목코드 또는 티커를 입력해주세요.")
    fetched = await asyncio.gather(
        *[asyncio.to_thread(fetch_quote_snapshot, ticker) for ticker in symbols],
        return_exceptions=True,
    )
    results, errors = [], []
    for ticker, item in zip(symbols, fetched):
        if isinstance(item, Exception):
            errors.append({"ticker": ticker, "message": str(item)})
        elif item:
            results.append(item)
        else:
            errors.append({"ticker": ticker, "message": "현재 시세를 가져오지 못했습니다."})
    return {
        "results": results,
        "errors": errors,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Chart 5m with daily fallback",
        "dataContract": {
            "price": "latest available provider quote or latest close fallback",
            "change": "percent change versus previous trading close",
            "asOf": "provider market timestamp when available",
            "currency": "provider currency",
            "missingValue": "null/omitted; zero is not used as a missing-value substitute",
        },
    }


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
    stocks = [by_ticker[t] for t in ticker_list if t in by_ticker]
    return {
        "stocks": stocks,
        "errors": errors,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance Chart",
        "comparisonBasis": {
            "returnFormula": "(last_adjusted_or_close - first_adjusted_or_close) / first * 100",
            "priceBasis": "provider adjusted close when available; otherwise close",
            "currencyMode": "local currency per symbol; no FX conversion",
            "calendarMode": "per-symbol available trading observations",
            "startPolicy": "each symbol uses its first available observation in the requested period",
            "missingObservationPolicy": "missing observations are omitted; no interpolation",
            "totalReturnVerified": False,
        },
    }


def _load_home_insight_sources():
    """Load large Home support JSON once per process/TTL instead of on every request."""
    import json
    from pathlib import Path

    now = time.time()
    cached = HOME_INSIGHTS_SOURCE_CACHE.get("data")
    if cached and now - HOME_INSIGHTS_SOURCE_CACHE.get("timestamp", 0.0) < HOME_INSIGHTS_SOURCE_TTL:
        return cached

    data_dir = Path(__file__).resolve().parent / "static" / "data"
    data = {
        "screener": json.loads((data_dir / "screener.json").read_text(encoding="utf-8")),
        "consensus": json.loads((data_dir / "consensus_cache.json").read_text(encoding="utf-8")),
        "valuation": json.loads((data_dir / "valuation_cache.json").read_text(encoding="utf-8")),
        "macro": json.loads((data_dir / "macro_cache.json").read_text(encoding="utf-8")),
    }
    HOME_INSIGHTS_SOURCE_CACHE["data"] = data
    HOME_INSIGHTS_SOURCE_CACHE["timestamp"] = now
    return data


@app.get("/api/home-insights")
async def home_insights(tickers: str = ""):
    """Return only the screener rows needed by Home, backed by a parsed-source memory cache."""
    try:
        sources = _load_home_insight_sources()
        screener = sources["screener"]
        consensus = sources["consensus"]
        valuation = sources["valuation"]
        macro = sources["macro"]

        requested = {x.strip().upper() for x in tickers.split(",") if x.strip()}
        consensus_quotes = consensus.get("quotes") or {}
        keep = set(consensus_quotes) | requested
        stocks = screener.get("stocks") or []

        def number(value, fallback=-1e30):
            try:
                return float(value)
            except (TypeError, ValueError):
                return fallback

        volume_rows = sorted(stocks, key=lambda row: number(row.get("volumeRatio")), reverse=True)[:5]
        signal_rows = [
            row for row in stocks
            if number(row.get("score")) >= 52
            and (
                number(row.get("volumeRatio")) >= 1.2
                or row.get("cross20") is True
                or row.get("aligned") is True
                or number(row.get("rsi14"), 1e30) <= 35
            )
        ]
        signal_rows.sort(
            key=lambda row: (number(row.get("score")), number(row.get("volumeRatio"))),
            reverse=True,
        )
        keep.update(str(row.get("symbol") or "").upper() for row in volume_rows + signal_rows[:12])
        compact_stocks = [row for row in stocks if str(row.get("symbol") or "").upper() in keep]

        payload = {
            "screener": {
                "stocks": compact_stocks,
                "tradeDate": screener.get("tradeDate"),
                "generatedAt": screener.get("generatedAt"),
            },
            "consensus": {
                "quotes": consensus_quotes,
                "generatedAt": consensus.get("generatedAt"),
            },
            "valuation": {
                "quotes": valuation.get("quotes") or {},
                "generatedAt": valuation.get("generatedAt"),
            },
            "macro": macro,
            "cacheMode": "parsed-source-memory",
        }
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=3600"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"home insights unavailable: {exc}")


@app.get("/api/home-bootstrap")
async def home_bootstrap():
    """Return the small set of precomputed files needed by the home PICK widget in one request."""
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent / "static" / "data"
    try:
        rankings = json.loads((data_dir / "ai_daily_rankings.json").read_text(encoding="utf-8"))
        recommendations = json.loads((data_dir / "ai_recommendations.json").read_text(encoding="utf-8"))
        days = rankings.get("days") or []
        day = max(days, key=lambda item: str(item.get("tradeDate") or ""), default=None)
        versions = [str(rankings.get("updated") or ""), str(recommendations.get("updated") or "")]
        payload = {
            "day": day,
            "recommendations": recommendations.get("recommendations") or [],
            "version": max(versions),
        }
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "no-cache, max-age=0, must-revalidate"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"home bootstrap unavailable: {exc}")


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
        if cached and now - MARKET_NOW_CACHE.get("timestamp", 0) < MARKET_NOW_REFRESH_GUARD:
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
                    "previousClose": row.get("previousClose"),
                    "change": row.get("change"),
                    "currency": row.get("currency"),
                    "asOf": row.get("asOf"),
                    "sessionDate": row.get("sessionDate"),
                    "previousSessionDate": row.get("previousSessionDate"),
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
            audit = {row.get("ticker"): row for row in results if row.get("ticker") in {"^GSPC", "^IXIC"}}
            if audit:
                print("[MARKET_AUDIT] " + json.dumps(audit, ensure_ascii=False, sort_keys=True))
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
async def heatmap_data(fresh: bool = False):
    """Return the shared Home snapshot for the visual heatmap.

    The endpoint intentionally does not fan out into per-symbol provider calls.
    Home remains cache-first; stale data is revalidated by the existing
    HOME_SNAPSHOT stale-while-revalidate path.
    """
    payload = await home_snapshot(fresh=fresh)
    heatmap = payload.get("heatmap") or {"results": []}
    return {
        "results": heatmap.get("results") or [],
        "generatedAt": payload.get("generatedAt"),
        "source": payload.get("source"),
        "cacheAgeSec": payload.get("cacheAgeSec"),
        "refreshing": payload.get("refreshing"),
        "cacheMode": payload.get("cacheMode"),
    }

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


MACRO_DISPLAY_META = {
    "T10Y2Y": {"unit": "%p", "changeUnit": "bp", "changeBasis": "previous observation", "category": "rates"},
    "T10Y3M": {"unit": "%p", "changeUnit": "bp", "changeBasis": "previous observation", "category": "rates"},
    "BAMLH0A0HYM2": {"unit": "%p", "changeUnit": "bp", "changeBasis": "previous observation", "category": "risk"},
    "DFII10": {"unit": "%", "changeUnit": "bp", "changeBasis": "previous observation", "category": "rates"},
    "T10YIE": {"unit": "%", "changeUnit": "bp", "changeBasis": "previous observation", "category": "prices"},
    "PCEPI": {"unit": "% YoY", "changeUnit": "bp", "changeBasis": "previous monthly observation", "category": "prices"},
    "PCETRIM12M159SFRBDAL": {"unit": "% YoY", "changeUnit": "bp", "changeBasis": "previous monthly observation", "category": "prices"},
    "UNRATE": {"unit": "%", "changeUnit": "bp", "changeBasis": "previous observation", "category": "labor"},
    "RSAFS": {"unit": "USD million", "changeUnit": "%", "changeBasis": "previous observation", "category": "activity"},
    "RRPONTSYD": {"unit": "USD billion", "changeUnit": "%", "changeBasis": "previous observation", "category": "liquidity"},
    "WALCL": {"unit": "USD million", "changeUnit": "%", "changeBasis": "previous observation", "category": "liquidity"},
    "WTREGEN": {"unit": "USD million", "changeUnit": "%", "changeBasis": "previous observation", "category": "liquidity"},
    "M2SL": {"unit": "USD billion", "changeUnit": "%", "changeBasis": "previous observation", "category": "liquidity"},
    "FEDTARGET": {"unit": "% range", "changeUnit": "bp", "changeBasis": "previous FOMC target change", "category": "rates"},
    "DFF": {"unit": "%", "changeUnit": "bp", "changeBasis": "previous daily observation", "category": "rates"},
    "^VIX": {"unit": "index point", "changeUnit": "pt", "changeBasis": "previous observation", "category": "risk"},
}


def _macro_display_row(row):
    symbol = row.get("original_symbol") or row.get("symbol")
    meta = MACRO_DISPLAY_META.get(symbol, {})
    delta = row.get("delta")
    display_change = None
    try:
        if meta.get("changeUnit") == "bp" and delta is not None:
            display_change = round(float(delta) * 100, 2)
        elif meta.get("changeUnit") == "pt" and delta is not None:
            display_change = round(float(delta), 4)
        elif row.get("change") is not None:
            display_change = round(float(row.get("change")), 2)
    except (TypeError, ValueError):
        display_change = None
    return {
        **row,
        **meta,
        "observedAt": row.get("asOf"),
        "displayChange": display_change,
        "status": "stale" if row.get("stale") else "current",
    }


def generate_macro_summary(ordered_results, net_liquidity):
    """Describe the macro regime using Fed policy, inflation and market stress.

    This is a descriptive traffic-light state, not a forecast or trading signal.
    """
    rows = {
        (item.get("original_symbol") or item.get("symbol")): item
        for item in ordered_results
        if isinstance(item, dict)
    }

    scores = {}
    details = []

    def value(symbol):
        try:
            raw = rows.get(symbol, {}).get("value")
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    # 1) Inflation pressure: the Fed's 2% objective makes this the primary policy axis.
    pce = value("PCEPI")
    trimmed = value("PCETRIM12M159SFRBDAL")
    bei = value("T10YIE")
    inflation_values = [x for x in (pce, trimmed) if x is not None]
    if inflation_values:
        inflation_anchor = max(inflation_values)
        if inflation_anchor >= 3.0:
            scores["물가"] = -2
            details.append(f"물가 압력 높음(PCE {pce:.1f}%)" if pce is not None else "물가 압력 높음")
        elif inflation_anchor >= 2.4:
            scores["물가"] = -1
            details.append(f"물가 2% 목표 상회({inflation_anchor:.1f}%)")
        elif inflation_anchor >= 1.8:
            scores["물가"] = 1
            details.append(f"물가 2% 부근({inflation_anchor:.1f}%)")
        else:
            scores["물가"] = 0
            details.append(f"물가 낮음({inflation_anchor:.1f}%)")
    if bei is not None:
        if bei >= 2.6:
            scores["기대물가"] = -1
            details.append(f"기대인플레 {bei:.1f}%↑")
        elif bei <= 2.1:
            scores["기대물가"] = 1
            details.append(f"기대인플레 {bei:.1f}% 안정")
        else:
            scores["기대물가"] = 0

    # 2) Fed stance: target range and most recent discrete FOMC move.
    target = rows.get("FEDTARGET") or {}
    dff = value("DFF")
    try:
        lower = float(target.get("targetLower"))
        upper = float(target.get("targetUpper"))
        move_bp = float(target.get("moveBp") or 0)
        target_mid = (lower + upper) / 2.0
        if move_bp >= 12.5:
            scores["Fed"] = -2
            stance = f"Fed {lower:.2f}~{upper:.2f}% · 최근 +{move_bp:.0f}bp"
        elif move_bp <= -12.5:
            scores["Fed"] = 1
            stance = f"Fed {lower:.2f}~{upper:.2f}% · 최근 {move_bp:.0f}bp"
        elif target_mid >= 4.5:
            scores["Fed"] = -1
            stance = f"Fed {lower:.2f}~{upper:.2f}% · 높은 금리 유지"
        else:
            scores["Fed"] = 0
            stance = f"Fed {lower:.2f}~{upper:.2f}% · 동결"
        if dff is not None:
            stance += f" · EFFR {dff:.2f}%"
        details.append(stance)
    except (TypeError, ValueError):
        if dff is not None:
            scores["Fed"] = 0
            details.append(f"EFFR {dff:.2f}%")

    # 3) Labor/growth: rising unemployment or weak retail activity adds caution.
    unrate = value("UNRATE")
    if unrate is not None:
        unrow = rows.get("UNRATE") or {}
        try:
            ud = float(unrow.get("delta") or 0)
        except (TypeError, ValueError):
            ud = 0
        if unrate >= 5.0 or (unrate >= 4.5 and ud >= 0.2):
            scores["고용"] = -2
            details.append(f"실업률 {unrate:.1f}% 약화")
        elif unrate >= 4.5:
            scores["고용"] = -1
            details.append(f"실업률 {unrate:.1f}% 주의")
        else:
            scores["고용"] = 1

    retail = rows.get("RSAFS") or {}
    try:
        retail_change = float(retail.get("change"))
    except (TypeError, ValueError):
        retail_change = None
    if retail_change is not None:
        if retail_change <= -1.0:
            scores["소비"] = -1
            details.append("소매판매 둔화")
        elif retail_change >= 1.0:
            scores["소비"] = 1

    # 4) Financial stress: credit and volatility can offset or amplify policy pressure.
    hy = value("BAMLH0A0HYM2")
    vix = value("^VIX")
    if hy is not None:
        if hy >= 5.0:
            scores["신용"] = -2
            details.append(f"신용스프레드 {hy:.1f}% 위험")
        elif hy >= 4.0:
            scores["신용"] = -1
            details.append(f"신용스프레드 {hy:.1f}% 주의")
        else:
            scores["신용"] = 1
            details.append("신용스프레드 안정")
    if vix is not None:
        if vix >= 30:
            scores["VIX"] = -2
            details.append(f"VIX {vix:.0f} 공포")
        elif vix >= 20:
            scores["VIX"] = -1
            details.append(f"VIX {vix:.0f} 경계")
        elif vix < 17:
            scores["VIX"] = 1
            details.append(f"VIX {vix:.0f} 안정")
        else:
            scores["VIX"] = 0

    # 5) Liquidity is useful context, but receives less weight than Fed/inflation stress.
    if net_liquidity and not net_liquidity.get("error"):
        try:
            nl_change = float(net_liquidity.get("change") or 0)
        except (TypeError, ValueError):
            nl_change = 0
        if nl_change >= 1.0:
            scores["유동성"] = 1
            details.append(f"순유동성 +{nl_change:.1f}%")
        elif nl_change <= -1.0:
            scores["유동성"] = -1
            details.append(f"순유동성 {nl_change:.1f}%")

    if not scores:
        return {"text": "지표 데이터를 가져오는 중입니다.", "level": "yellow"}

    total = sum(scores.values())
    negative_axes = sum(1 for score in scores.values() if score < 0)
    severe_axes = sum(1 for score in scores.values() if score <= -2)

    # Red requires broad or severe stress; mixed policy/inflation pressure is yellow.
    if severe_axes >= 2 or total <= -5 or negative_axes >= 4:
        level = "red"
        judgment = "현재는 물가·정책·금융 스트레스 중 부정 압력이 넓게 나타납니다."
    elif total <= 0 or negative_axes >= 2:
        level = "yellow"
        judgment = "물가·통화정책 부담과 금융시장 안정 신호가 함께 나타납니다."
    else:
        level = "green"
        judgment = "현재는 금융 스트레스가 낮고 거시 지표의 안정 신호가 상대적으로 많습니다."

    return {
        "text": " | ".join(details[:7]) + f" → {judgment}",
        "level": level,
        "method": "descriptive Fed-policy/inflation/labor/financial-stress regime",
        "components": scores,
        "notice": "시장 환경을 설명하기 위한 요약이며 투자 행동을 권유하지 않습니다. 향후 FOMC 결정을 예측하는 신호도 아닙니다.",
    }


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
        _macro_display_row(row)
        for row in (payload.get("results") or [])
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
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "cacheMode": "precomputed",
        "dataContract": {
            "observedAt": "source observation date for each indicator",
            "generatedAt": "cache collection/build time",
            "displayChange": "change versus the previous available observation using each row's changeUnit",
            "missingValue": "null/omitted; zero is not used as a missing-value substitute",
        },
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
    """Best-effort cold-start seed from the persistent home snapshot."""
    if HOME_SNAPSHOT_CACHE.get("data"):
        return HOME_SNAPSHOT_CACHE["data"]
    results = []
    try:
        import json as _json
        snapshot_path = os.path.join(os.path.dirname(__file__), "static", "data", "home_snapshot.json")
        with open(snapshot_path, "r", encoding="utf-8") as f:
            disk_snapshot = _json.load(f)
        results = [{**row, "stale": True} for row in (disk_snapshot.get("heatmap", {}).get("results") or []) if isinstance(row, dict)]
        if results:
            HOME_SNAPSHOT_CACHE["data"] = {
                "heatmap": {"results": results},
                "macro": MACRO_CACHE.get("data"),
                "generatedAt": disk_snapshot.get("generatedAt"),
                "source": disk_snapshot.get("source") or "disk-seed",
                "errors": disk_snapshot.get("errors") or [],
            }
            HOME_SNAPSHOT_CACHE["timestamp"] = 0.0
            return HOME_SNAPSHOT_CACHE["data"]
    except Exception as exc:
        print(f"[HOME] persistent snapshot unavailable: {exc}")
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
        # A disk seed is safe to serve but is not a fresh network snapshot.
        # Timestamp zero lets startup revalidate without delaying app readiness.
        HOME_SNAPSHOT_CACHE["timestamp"] = 0.0
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
        # A force request may bypass the TTL, but it must not repeat work that a
        # concurrent request just completed while this caller waited on the lock.
        if cached and now - HOME_SNAPSHOT_CACHE.get("timestamp", 0) < HOME_SNAPSHOT_REFRESH_GUARD:
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
                    "marketCap": row.get("marketCap") or (previous_rows.get(ticker) or {}).get("marketCap") or 0,
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


@app.get("/api/valuation-bands")
async def valuation_bands_data(tickers: str, years: int = Query(default=3, ge=1, le=10)):
    """Batch valuation-band lookup so Home needs one request, not up to eight."""
    symbols = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
    if not symbols or len(symbols) > 8:
        raise HTTPException(400, "밸류에이션 밴드는 1개 이상 8개 이하 종목을 조회할 수 있습니다.")
    if any(not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,19}", t) for t in symbols):
        raise HTTPException(400, "유효한 종목코드 또는 티커를 입력해주세요.")

    fetched = await asyncio.gather(
        *[asyncio.to_thread(fetch_valuation_bands, symbol, years) for symbol in symbols],
        return_exceptions=True,
    )
    bands, errors = {}, []
    for symbol, item in zip(symbols, fetched):
        if isinstance(item, Exception):
            errors.append({"ticker": symbol, "message": str(item)})
        elif item:
            bands[symbol] = item
        else:
            errors.append({"ticker": symbol, "message": "밸류에이션 밴드를 계산하지 못했습니다."})
    return {"bands": bands, "errors": errors, "years": years}


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
