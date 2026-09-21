from concurrent.futures import ThreadPoolExecutor
from threading import Event, Barrier
import pytest
from request_coalescing import singleflight

def test_concurrent_requests_share_one_provider_call():
    entered, release = Event(), Event()
    calls = []
    @singleflight
    def provider(symbol):
        calls.append(symbol)
        entered.set()
        assert release.wait(2)
        return {'price': 42}
    with ThreadPoolExecutor(8) as executor:
        first = executor.submit(provider, 'AAPL')
        assert entered.wait(1)
        rest = [executor.submit(provider, 'AAPL') for _ in range(6)]
        release.set()
        assert first.result() == {'price': 42}
        assert all(f.result() == {'price': 42} for f in rest)
    # A burst is deduplicated, but completed results are not stored forever.
    assert len(calls) == 1
    provider('AAPL')
    assert len(calls) == 2

def test_failures_do_not_poison_the_next_request():
    calls = []
    @singleflight
    def provider(symbol):
        calls.append(symbol)
        if len(calls) == 1:
            raise ValueError('provider unavailable')
        return symbol
    with pytest.raises(ValueError):
        provider('AAPL')
    assert provider('AAPL') == 'AAPL'

def test_distinct_symbols_do_not_serialize():
    barrier = Barrier(2)
    @singleflight
    def provider(symbol):
        barrier.wait(timeout=2)
        return symbol
    with ThreadPoolExecutor(2) as executor:
        a, b = executor.submit(provider, 'AAPL'), executor.submit(provider, 'NVDA')
        assert [a.result(), b.result()] == ['AAPL', 'NVDA']
