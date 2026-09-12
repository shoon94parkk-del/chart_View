"""Offline regression tests for API boundaries and market data integrity."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
import main
import market_service as market

client = TestClient(main.app)


@pytest.mark.parametrize('path', [
    '/api/compare?tickers=AAPL&start=2026-09-12&end=2026-01-01',
    '/api/compare?tickers=AAPL&start=2026-02-30&end=2026-03-01',
    '/api/compare?tickers=AAPL&start=2026-01-01',
    '/api/compare?tickers=AAPL&period=unsupported',
    '/api/compare?tickers=A,B,C,D,E,F,G',
    '/api/valuation?tickers=%3Cscript%3E',
    '/api/compare?tickers=',
    '/api/consensus?ticker=../secret',
])
def test_invalid_requests_never_reach_provider(path):
    with patch.object(main, 'fetch_compare_stock') as provider:
        assert client.get(path).status_code == 400
        provider.assert_not_called()


def test_compare_deduplicates_and_keeps_partial_success():
    def quote(ticker, *args):
        return {'ticker': ticker, 'data': []} if ticker == 'AAPL' else None
    with patch.object(main, 'fetch_compare_stock', side_effect=quote) as provider:
        data = client.get('/api/compare?tickers=aapl,AAPL,NVDA').json()
    assert [r['ticker'] for r in data['stocks']] == ['AAPL']
    assert [r['ticker'] for r in data['errors']] == ['NVDA']
    assert provider.call_count == 2


def test_search_handles_ascii_korean_company_and_rejects_markup():
    assert client.get('/api/search?q=JYP').json()['results'][0]['symbol'] == '035900.KQ'
    assert client.get('/api/search?q=035900').json()['results'][0]['market'] == 'KOSDAQ'
    assert client.get('/api/search', params={'q': '<img src=x onerror=alert(1)>'}).json()['results'] == []
    assert client.get('/api/search', params={'q': '존재하지않는회사'}).json()['results'] == []


@pytest.mark.parametrize('value', [float('nan'), float('inf'), '-inf', None, ''])
def test_nonfinite_market_values_are_missing(value):
    assert market._number(value) is None
    assert market._positive(value) is None


def test_zero_eps_is_not_replaced_by_another_source():
    with patch.object(market, '_valuation_cache', {}), \
         patch.object(market, '_chart_result', return_value={'meta': {'regularMarketPrice': 100}}), \
         patch.object(market, '_fundamentals', return_value={'trailingDilutedEPS': 5}), \
         patch.object(market, '_cached_quote_summary', return_value={'defaultKeyStatistics': {'trailingEps': {'raw': 0}}}), \
         patch.object(market, '_naver_valuation', return_value={}):
        assert market.fetch_valuation_snapshot('TEST')['trailingEPS'] == 0


def test_missing_previous_close_is_not_flat_change():
    chart = {'meta': {'regularMarketPrice': 100, 'regularMarketTime': 1789142400},
             'indicators': {'quote': [{'close': [100]}]}}
    with patch.object(market, '_quote_cache', {}), patch.object(market, '_chart_result', return_value=chart):
        result = market.fetch_quote_snapshot('TEST')
    assert result['price'] == 100
    assert result['change'] is None
    assert result['asOf'].startswith('2026-09-11')


def test_compare_cache_is_bounded():
    chart = {'meta': {}, 'timestamp': [1, 2], 'indicators': {'quote': [{'close': [10, 11]}]}}
    with patch.object(market, '_compare_cache', {}), patch.object(market, '_chart_result', return_value=chart):
        for i in range(70):
            assert market.fetch_compare_stock(f'T{i}')['return'] == 10
        assert len(market._compare_cache) == 64


def test_seed_keeps_original_data_date():
    cache = {'data': None, 'timestamp': 0, 'refreshing': False}
    disk = json.loads(Path('static/data/valuation_cache.json').read_text())
    with patch.object(main, 'HOME_SNAPSHOT_CACHE', cache):
        data = main._seed_home_snapshot_from_disk()
    assert data['generatedAt'] == disk['generatedAt']
    assert all(r['stale'] for r in data['heatmap']['results'])


def test_failed_refresh_keeps_quote_date_and_marks_stale():
    old = {'ticker': 'AAPL', 'price': 100, 'asOf': '2026-09-10T20:00:00+00:00'}
    cache = {'data': {'heatmap': {'results': [old]}}, 'timestamp': 0, 'refreshing': False}
    with patch.object(main, 'HOME_SNAPSHOT_CACHE', cache), \
         patch.object(main, 'HOME_SNAPSHOT_LOCK', asyncio.Lock()), \
         patch.object(main, 'HOME_MAJOR_TICKERS', ['AAPL']), \
         patch.object(main, 'fetch_quote_snapshot', return_value=None):
        data = asyncio.run(main._refresh_home_snapshot(force=True))
    assert data['heatmap']['results'] == [{**old, 'stale': True}]
    assert old.get('stale') is None


def test_local_assets_exist():
    import re
    html = client.get('/').text
    assert client.get('/health').json()['revision']
    for path in re.findall(r'(?:src|href)="(/static/[^"?]+)', html):
        assert client.get(path).status_code == 200, path
