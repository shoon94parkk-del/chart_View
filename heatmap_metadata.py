"""Classification metadata only: no quote values from legacy layout files."""
import math


def us_universe(payload, names, limit=40):
    sectors = payload.get("sectors") or []
    entries = sectors.items() if isinstance(sectors, dict) else [(None, item) for item in sectors]
    rows, seen = [], set()
    for key, sector in entries:
        label = key if isinstance(sector, list) else sector.get("name") or key
        stocks = sector if isinstance(sector, list) else sector.get("stocks") or sector.get("data") or []
        for row in stocks:
            ticker = str(row.get("ticker") or "").strip().upper()
            try:
                cap = float(row.get("marketCap"))
            except (TypeError, ValueError):
                continue
            if not ticker or ticker in seen or cap <= 0 or not math.isfinite(cap):
                continue
            seen.add(ticker)
            rows.append({"ticker": ticker, "name": names.get(ticker) or ticker, "market": "US",
                         "marketCap": cap, "sector": label, "sectorSource": "미국 히트맵 산업 분류"})
    rows.sort(key=lambda row: row["marketCap"], reverse=True)
    # Keep the same quote-request budget while covering every available sector.
    selected, covered = [], set()
    for row in rows:
        if row["sector"] not in covered and len(selected) < limit:
            selected.append(row)
            covered.add(row["sector"])
    chosen = {row["ticker"] for row in selected}
    for row in rows:
        if row["ticker"] not in chosen and len(selected) < limit:
            selected.append(row)
    return sorted(selected, key=lambda row: row["marketCap"], reverse=True)[:limit]


def korean_metadata(screener):
    return {str(row["symbol"]).upper(): {"industry": row.get("industry"), "mainProducts": row.get("mainProducts"),
            "sectorSource": "KRX 업종·주요제품"} for row in screener.get("stocks", []) if row.get("symbol")}
def quote_order(us_rows, kr_tickers):
    """Fetch one large company per US sector before the rest of the same budget."""
    sectors, representatives = set(), []
    for row in sorted(us_rows, key=lambda row: -(row.get('marketCap') or 0)):
        if row.get('sector') and row['sector'] not in sectors:
            sectors.add(row['sector']); representatives.append(row['ticker'])
    return list(dict.fromkeys(representatives + list(kr_tickers) + [row['ticker'] for row in us_rows]))
