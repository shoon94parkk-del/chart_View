import market_service as market


def test_valuation_exposes_ttm_roa_on_same_basis_as_greenblatt_reference(monkeypatch):
    monkeypatch.setattr(market, "_chart_result", lambda *args, **kwargs: {
        "meta": {"regularMarketPrice": 100, "currency": "KRW", "regularMarketTime": 1790899200},
        "indicators": {"quote": [{"close": [100]}]},
    })
    monkeypatch.setattr(market, "_fundamentals", lambda symbol: {
        "trailingMarketCap": 1000,
        "trailingPeRatio": 10,
        "trailingBasicEPS": 10,
        "trailingNetIncome": 25,
        "quarterlyTotalAssets": 100,
        "quarterlyStockholdersEquity": 50,
    })
    monkeypatch.setattr(market, "_cached_quote_summary", lambda symbol: None)
    monkeypatch.setattr(market, "_quote_summary", lambda symbol: {
        "price": {"currency": "KRW", "shortName": "시험기업"}
    })
    monkeypatch.setattr(market, "_naver_valuation", lambda symbol: {})
    monkeypatch.setattr(market, "_local_names", lambda: {})

    row = market.fetch_valuation_snapshot("000001.KS", force=True)

    assert row["trailingPE"] == 10
    assert row["roa"] == 25
    assert row["fieldMeta"]["trailingPE"]["period"] == "TTM"
    assert row["fieldMeta"]["roa"]["period"] == "TTM net income / latest reported assets"
    assert row["fieldMeta"]["roa"]["method"] == "trailing net income / latest assets"
