from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, get_ident
from types import SimpleNamespace

import pytest
import realtime_korea as rk


@pytest.fixture(autouse=True)
def clean_quote_cache():
    with rk._quote_lock:
        rk._quote_cache.clear()
    yield
    with rk._quote_lock:
        rk._quote_cache.clear()


def overlapping_misses(monkeypatch, count):
    original = rk._cache_get
    first_read = set()
    lock, barrier = Lock(), Barrier(count)

    def cache_get(symbol):
        with lock:
            first = get_ident() not in first_read
            first_read.add(get_ident())
        if first:
            # Every caller has already seen an expired/missing entry before
            # the shared provider finishes. Inner owner checks stay genuine.
            barrier.wait(timeout=3)
            return None
        return original(symbol)

    monkeypatch.setattr(rk, '_cache_get', cache_get)


@pytest.mark.parametrize('symbol,fetch,basic', [
    ('005930.KS', rk.fetch_korean_stock_quote, '_basic_stock_quote'),
    ('^KS11', rk.fetch_korean_index_quote, '_basic_index_quote'),
])
def test_simultaneous_canonical_korean_misses_share_one_quote_and_isolate_callers(monkeypatch, symbol, fetch, basic):
    overlapping_misses(monkeypatch, 6)
    entered, release = Event(), Event()
    calls = []
    row = {'ticker': symbol, 'price': 103700, 'change': 2.37,
           'asOf': '2026-10-13T15:30:00+09:00', 'source': 'Naver Finance',
           'currency': 'KRW', 'priceBasis': 'regular_close'}

    def provider(ticker):
        calls.append(ticker)
        entered.set()
        assert release.wait(3)
        return dict(row)

    monkeypatch.setattr(rk, basic, provider)
    with ThreadPoolExecutor(6) as executor:
        futures = [executor.submit(fetch, symbol.lower() if i % 2 else symbol) for i in range(6)]
        try:
            assert entered.wait(3)
        finally:
            release.set()
        results = [future.result(timeout=3) for future in futures]
    assert calls == [symbol]
    assert all(result == row for result in results)
    results[0]['price'] = 1
    assert all(result['price'] == row['price'] for result in results[1:])
    assert rk._quote_cache[symbol][1] == row


def test_home_compare_and_valuation_share_the_same_korean_provider_work(monkeypatch):
    overlapping_misses(monkeypatch, 3)
    entered, release = Event(), Event()
    calls = []
    row = {'ticker': '005930.KS', 'price': 103700, 'change': 2.37,
           'asOf': '2026-10-13T15:30:00+09:00', 'source': 'Naver Finance', 'currency': 'KRW'}

    def provider(ticker):
        calls.append(ticker); entered.set()
        assert release.wait(3)
        return dict(row)

    monkeypatch.setattr(rk, '_basic_stock_quote', provider)
    module = SimpleNamespace(fetch_quote_snapshot=lambda symbol: pytest.fail('unexpected Yahoo fallback'),
        fetch_compare_stock=lambda symbol: {'price': 100000, 'data': [{'time': '2026-10-12', 'value': 0}]},
        fetch_valuation_snapshot=lambda symbol: {'price': 100000, 'fieldMeta': {}})
    rk.install_patch(module)
    with ThreadPoolExecutor(3) as executor:
        futures = [executor.submit(fn, '005930.KS') for fn in
                   (module.fetch_quote_snapshot, module.fetch_compare_stock, module.fetch_valuation_snapshot)]
        try:
            assert entered.wait(3)
        finally:
            release.set()
        results = [future.result(timeout=3) for future in futures]
    assert calls == ['005930.KS']
    assert all(result['price'] == 103700 for result in results)
    assert results[0]['asOf'] == row['asOf']
    assert results[1]['quoteAsOf'] == row['asOf']
    assert results[2]['fieldMeta']['price']['asOf'] == row['asOf']


def test_existing_five_second_cache_expires_without_advancing_observation_dates(monkeypatch):
    clock, calls = [100.0], []
    monkeypatch.setattr(rk.time, 'monotonic', lambda: clock[0])

    def provider(symbol):
        calls.append(symbol)
        return {'ticker': symbol, 'price': 100 + len(calls), 'asOf': f'actual-observation-{len(calls)}'}

    monkeypatch.setattr(rk, '_basic_stock_quote', provider)
    first = rk.fetch_korean_stock_quote('005930.KS')
    clock[0] += rk.QUOTE_TTL_SECONDS - .01
    assert rk.fetch_korean_stock_quote('005930.KS') == first
    assert rk._quote_cache['005930.KS'][0] == 100.0
    clock[0] += .02
    second = rk.fetch_korean_stock_quote('005930.KS')
    assert len(calls) == 2
    assert second['price'] == 102 and second['asOf'] == 'actual-observation-2'
    assert first['asOf'] == 'actual-observation-1'


def test_provider_failure_leaves_next_korean_request_retryable(monkeypatch):
    calls = []
    def basic(symbol):
        calls.append('basic')
        if len(calls) == 1: raise RuntimeError('basic unavailable')
        return {'ticker': symbol, 'price': 123, 'asOf': 'actual-observation'}
    def polling(symbol):
        calls.append('polling'); raise ValueError('polling unavailable')
    monkeypatch.setattr(rk, '_basic_stock_quote', basic)
    monkeypatch.setattr(rk, '_polling_stock_quote', polling)
    with pytest.raises(ValueError, match='polling unavailable'):
        rk.fetch_korean_stock_quote('005930.KS')
    assert '005930.KS' not in rk._quote_cache
    assert rk.fetch_korean_stock_quote('005930.KS')['price'] == 123
    assert calls == ['basic', 'polling', 'basic']


def test_different_korean_symbols_can_use_existing_provider_slots_concurrently(monkeypatch):
    barrier = Barrier(2)
    def provider(symbol):
        barrier.wait(timeout=3)
        return {'ticker': symbol, 'price': 123, 'asOf': 'actual-observation'}
    monkeypatch.setattr(rk, '_basic_stock_quote', provider)
    with ThreadPoolExecutor(2) as executor:
        futures = [executor.submit(rk.fetch_korean_stock_quote, symbol) for symbol in ('005930.KS', '000660.KS')]
        assert [future.result(timeout=3)['ticker'] for future in futures] == ['005930.KS', '000660.KS']
