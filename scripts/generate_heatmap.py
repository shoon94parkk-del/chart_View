"""
히트맵 데이터 생성 스크립트
GitHub Actions에서 주기적으로 실행하여 정적 JSON 파일 생성
"""

import json
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os

# S&P 500 섹터별 종목 (상위 100개)
SECTOR_STOCKS = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'AMD', 'INTC', 'CSCO'],
    'Communication': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS'],
    'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'LOW', 'TJX', 'BKNG'],
    'Financial': ['BRK-B', 'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'AXP', 'BLK'],
    'Healthcare': ['UNH', 'LLY', 'JNJ', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'CVS', 'ISRG'],
    'Industrials': ['GE', 'CAT', 'RTX', 'HON', 'UNP', 'BA', 'UPS', 'DE', 'LMT'],
    'Consumer Defensive': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'CL', 'MDLZ'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO'],
    'Real Estate': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'SPG'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE'],
    'Materials': ['LIN', 'APD', 'SHW', 'FCX', 'NEM', 'ECL']
}

def fetch_stock(ticker):
    """개별 종목 데이터 가져오기"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        df = stock.history(period="5d")
        
        if df.empty or len(df) < 2:
            return None
        
        prev_close = df["Close"].iloc[-2]
        last_close = df["Close"].iloc[-1]
        change = ((last_close - prev_close) / prev_close) * 100
        
        return {
            "ticker": ticker,
            "price": round(last_close, 2),
            "change": round(change, 2),
            "marketCap": info.get("marketCap", 1e9),
            "pe": round(info.get("trailingPE", 0), 1) if info.get("trailingPE") else None,
            "fwdPe": round(info.get("forwardPE", 0), 1) if info.get("forwardPE") else None
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def generate_heatmap_data():
    """히트맵 데이터 생성"""
    print(f"[{datetime.now()}] Starting heatmap data generation...")
    
    all_tickers = [t for tickers in SECTOR_STOCKS.values() for t in tickers]
    stock_data = {}
    
    # 병렬 처리
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_stock, t): t for t in all_tickers}
        for future in as_completed(futures):
            result = future.result()
            if result:
                stock_data[result["ticker"]] = result
    
    # 섹터별 그룹화
    sectors = []
    for sector_name, tickers in SECTOR_STOCKS.items():
        stocks = [stock_data[t] for t in tickers if t in stock_data]
        if stocks:
            stocks.sort(key=lambda x: x.get("marketCap", 0), reverse=True)
            sectors.append({"name": sector_name, "stocks": stocks})
    
    # 시가총액 기준 정렬
    sectors.sort(key=lambda x: sum(s.get("marketCap", 0) for s in x["stocks"]), reverse=True)
    
    result = {
        "sectors": sectors,
        "updated": datetime.now().isoformat(),
        "count": len(stock_data)
    }
    
    print(f"[{datetime.now()}] Generated data for {len(stock_data)} stocks")
    return result

def main():
    data = generate_heatmap_data()
    
    # 디렉토리 생성
    os.makedirs("static/data", exist_ok=True)
    
    # JSON 저장
    with open("static/data/heatmap.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"[{datetime.now()}] Saved to static/data/heatmap.json")

if __name__ == "__main__":
    main()
