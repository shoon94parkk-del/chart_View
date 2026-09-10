import yfinance as yf
import json

tickers = ["000660.KS", "005930.KS", "006400.KS", "AAPL", "SCHD"]
results = {}

for t in tickers:
    tick = yf.Ticker(t)
    info = tick.info
    results[t] = {
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "dividendYield": info.get("dividendYield"),
        "returnOnEquity": info.get("returnOnEquity"),
        "operatingMargins": info.get("operatingMargins"),
        "dividendRate": info.get("dividendRate")
    }

print(json.dumps(results, indent=2))
