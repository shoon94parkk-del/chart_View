from heatmap_metadata import us_universe, korean_metadata, quote_order

def test_quote_order_shows_sectors_early_without_expanding_the_universe():
    rows = [{'ticker': 'A', 'sector': 'Technology', 'marketCap': 100},
            {'ticker': 'B', 'sector': 'Technology', 'marketCap': 90},
            {'ticker': 'C', 'sector': 'Utilities', 'marketCap': 1}]
    assert quote_order(rows, ['KR', 'KR']) == ['A', 'C', 'KR', 'B']


def test_sector_coverage_is_preserved_without_legacy_prices():
    sectors = [{"name": "Technology", "stocks": [{"ticker": "A", "marketCap": 100, "price": 9, "change": 99}, {"ticker": "B", "marketCap": 90}]},
               {"name": "Utilities", "stocks": [{"ticker": "C", "marketCap": 1}]}]
    rows = us_universe({"sectors": sectors}, {}, limit=2)
    assert [r["ticker"] for r in rows] == ["A", "C"]
    assert rows[1]["sector"] == "Utilities"
    assert all("price" not in r and "change" not in r for r in rows)


def test_dictionary_layout_and_duplicate_symbols():
    rows = us_universe({"sectors": {"Energy": [{"ticker": "X", "marketCap": 10}, {"ticker": "X", "marketCap": 10}]}}, {"X": "Energy Co"})
    assert len(rows) == 1
    assert rows[0]["name"] == "Energy Co"
    assert rows[0]["sector"] == "Energy"


def test_korean_metadata_never_replaces_quote_or_daily_change():
    result = korean_metadata({"stocks": [{"symbol": "005930.KS", "industry": "전자", "mainProducts": "메모리", "price": 1, "change1d": 99, "ret5": 3, "date": "2026-10-01"}]})
    assert result["005930.KS"] == {"industry": "전자", "mainProducts": "메모리", "sectorSource": "KRX 업종·주요제품"}
