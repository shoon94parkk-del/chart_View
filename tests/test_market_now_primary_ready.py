"""Ordinary cold Home reads share one refresh without awaiting held extras."""
import asyncio

import httpx
import pytest

import main


PRIMARY = ['^KS11', '^KQ11', '^GSPC', '^IXIC']
EXTRAS = ['^TNX', '^VIX', 'CL=F', 'KRW=X']


def row(ticker):
    return {'ticker': ticker, 'price': 100, 'change': 1, 'previousClose': 99,
            'asOf': '2026-10-13T01:00:00+00:00', 'sessionDate': '2026-10-13',
            'previousSessionDate': '2026-10-12', 'currency': 'USD',
            'source': 'canonical fake provider'}


def setup_cache(monkeypatch):
    cache = {'data': None, 'timestamp': 0.0, 'refreshing': False, 'scheduled': False}
    monkeypatch.setattr(main, 'MARKET_NOW_CACHE', cache)
    monkeypatch.setattr(main, 'MARKET_NOW_LOCK', asyncio.Lock())
    monkeypatch.setattr(main, 'MARKET_NOW_TICKERS', PRIMARY + EXTRAS)
    return cache


def test_first_cold_http_read_returns_primary_while_fresh_read_waits_same_extras(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        primary_settled, extras_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls, settled = [], []

        async def provider(fn, ticker):
            assert fn is main.fetch_quote_snapshot
            calls.append(ticker)
            if ticker in EXTRAS:
                if all(value in calls for value in EXTRAS):
                    extras_started.set()
                await release.wait()
            else:
                settled.append(ticker)
                if len(settled) == 4:
                    primary_settled.set()
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            first = asyncio.create_task(client.get('/api/market-now'))
            fresh = None
            try:
                await asyncio.wait_for(primary_settled.wait(), 1)
                await asyncio.wait_for(extras_started.wait(), 1)
                response = await asyncio.wait_for(asyncio.shield(first), .2)
                assert response.status_code == 200
                payload = response.json()
                assert [item['ticker'] for item in payload['results']] == PRIMARY
                assert payload['refreshing'] is True
                assert payload['errors'] == []
                assert cache['timestamp'] == 0.0
                assert payload['cacheAgeSec'] is None
                assert all(item['asOf'] == row(item['ticker'])['asOf'] for item in payload['results'])

                fresh = asyncio.create_task(client.get('/api/market-now?fresh=true'))
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                assert not fresh.done()
                cached = await client.get('/api/market-now')
                assert cached.json()['results'] == payload['results']
                assert len(calls) == 8
                release.set()
                full = await asyncio.wait_for(fresh, 1)
                assert [item['ticker'] for item in full.json()['results']] == PRIMARY + EXTRAS
                assert full.json()['refreshing'] is False
                assert full.headers['cache-control'] == 'no-store'
                assert len(calls) == 8
                assert cache['timestamp'] > 0
                assert isinstance(full.json()['cacheAgeSec'], (int, float))
                assert cache.get('refreshTask') is None
                assert cache.get('primaryReady') is None
            finally:
                release.set()
                await asyncio.gather(first, *([fresh] if fresh else []), return_exceptions=True)

    asyncio.run(scenario())


def test_failed_primary_returns_pending_errors_before_exact_terminal_errors(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        primary_settled, release = asyncio.Event(), asyncio.Event()
        count = 0

        async def provider(_fn, ticker):
            nonlocal count
            if ticker in PRIMARY:
                count += 1
                if count == 4:
                    primary_settled.set()
                return None
            await release.wait()
            return None

        monkeypatch.setattr(main, '_background_market_call', provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            first = asyncio.create_task(client.get('/api/market-now'))
            try:
                await asyncio.wait_for(primary_settled.wait(), 1)
                pending = (await asyncio.wait_for(asyncio.shield(first), .2)).json()
                assert pending['results'] == []
                assert [error['ticker'] for error in pending['errors']] == PRIMARY
                assert pending['refreshing'] is True
                assert cache['timestamp'] == 0.0
                fresh = asyncio.create_task(client.get('/api/market-now?fresh=true'))
                release.set()
                result = (await asyncio.wait_for(fresh, 1)).json()
                assert result['results'] == []
                assert [error['ticker'] for error in result['errors']] == PRIMARY + EXTRAS
                assert result['refreshing'] is False
                assert cache.get('refreshTask') is None
            finally:
                release.set()
                await asyncio.gather(first, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize('hold_all', [False, True])
def test_cold_wait_budget_returns_only_observed_rows_and_keeps_owner(monkeypatch, hold_all):
    async def scenario():
        cache = setup_cache(monkeypatch)
        # The production budget is 2s; held providers, not elapsed speed, are the invariant.
        monkeypatch.setattr(main, 'MARKET_NOW_INITIAL_WAIT_SEC', .03, raising=False)
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def provider(_fn, ticker):
            calls.append(ticker)
            if len(calls) == 8:
                started.set()
            if hold_all or ticker == '^IXIC':
                await release.wait()
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            first = asyncio.create_task(client.get('/api/market-now'))
            fresh = None
            try:
                await asyncio.wait_for(started.wait(), 1)
                response = await asyncio.wait_for(asyncio.shield(first), .2)
                payload = response.json()
                expected = [] if hold_all else [ticker for ticker in PRIMARY + EXTRAS if ticker != '^IXIC']
                assert [item['ticker'] for item in payload['results']] == expected
                assert payload['refreshing'] is True
                assert payload['errors'] == []
                assert payload['cacheAgeSec'] is None
                assert response.headers['cache-control'] == 'no-store'
                assert 'market-ready;dur=' in response.headers['server-timing']
                assert 'market-handler;dur=' in response.headers['server-timing']
                assert cache['timestamp'] == 0.0
                assert not cache['refreshTask'].done()
                fresh = asyncio.create_task(client.get('/api/market-now?fresh=true'))
                await asyncio.sleep(0)
                assert not fresh.done()
                release.set()
                full = (await asyncio.wait_for(fresh, 1)).json()
                assert len(full['results']) == 8
                assert full['refreshing'] is False
                assert len(calls) == 8
            finally:
                release.set()
                await asyncio.gather(first, *([fresh] if fresh else []), return_exceptions=True)

    asyncio.run(scenario())


def test_cancelling_cold_http_waiter_does_not_cancel_shared_refresh(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        started, release = asyncio.Event(), asyncio.Event()
        calls, cancelled = [], []

        async def provider(_fn, ticker):
            calls.append(ticker)
            if len(calls) == 8:
                started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.append(ticker)
                raise
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            first = asyncio.create_task(client.get('/api/market-now'))
            try:
                await asyncio.wait_for(started.wait(), 1)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                assert cancelled == []
                assert cache['refreshing'] is True
                fresh = asyncio.create_task(client.get('/api/market-now?fresh=true'))
                await asyncio.sleep(0)
                release.set()
                full = (await asyncio.wait_for(fresh, 1)).json()
                assert len(full['results']) == 8
                assert len(calls) == 8
                assert cache['refreshing'] is False
                assert cache.get('refreshTask') is None
            finally:
                release.set()
                await asyncio.gather(first, return_exceptions=True)

    asyncio.run(scenario())


def test_concurrent_cold_and_fresh_http_waiters_share_one_owner(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        all_started, release_primary, release_extras = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = []

        async def provider(_fn, ticker):
            calls.append(ticker)
            if len(calls) == 8:
                all_started.set()
            await (release_primary if ticker in PRIMARY else release_extras).wait()
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            first = asyncio.create_task(client.get('/api/market-now'))
            second = asyncio.create_task(client.get('/api/market-now'))
            fresh = asyncio.create_task(client.get('/api/market-now?fresh=true'))
            try:
                await asyncio.wait_for(all_started.wait(), 1)
                assert len(calls) == 8
                assert not first.done() and not second.done() and not fresh.done()
                release_primary.set()
                responses = await asyncio.wait_for(asyncio.gather(first, second), 1)
                assert all([item['ticker'] for item in response.json()['results']] == PRIMARY for response in responses)
                assert not fresh.done()
                assert cache['timestamp'] == 0.0
                release_extras.set()
                result = (await asyncio.wait_for(fresh, 1)).json()
                assert len(result['results']) == 8
                assert len(calls) == 8
                assert cache.get('refreshTask') is None
            finally:
                release_primary.set()
                release_extras.set()
                await asyncio.gather(first, second, fresh, return_exceptions=True)

    asyncio.run(scenario())


def test_failed_primary_keeps_dated_fallback_and_error_while_extras_continue(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        previous = dict(row('^KQ11'), price=90, asOf='2026-10-12T01:00:00+00:00')
        cache['data'] = {'results': [previous], 'errors': []}
        cache['timestamp'] = 1.0
        primary_settled, release = asyncio.Event(), asyncio.Event()
        settled = []

        async def provider(_fn, ticker):
            if ticker in EXTRAS:
                await release.wait()
            else:
                settled.append(ticker)
                if len(settled) == 4:
                    primary_settled.set()
                if ticker == '^KQ11':
                    raise RuntimeError('fake index unavailable')
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            fresh = asyncio.create_task(client.get('/api/market-now?fresh=true'))
            try:
                await asyncio.wait_for(primary_settled.wait(), 1)
                response = (await client.get('/api/market-now')).json()
                values = {item['ticker']: item for item in response['results']}
                assert set(values) == set(PRIMARY)
                assert values['^KQ11'] == dict(previous, stale=True)
                assert [error['ticker'] for error in response['errors']] == ['^KQ11']
                assert response['refreshing'] is True
                assert cache['timestamp'] == 1.0
                assert not fresh.done()
                release.set()
                full = (await asyncio.wait_for(fresh, 1)).json()
                assert len(full['results']) == 8
                assert full['refreshing'] is False
            finally:
                release.set()
                await asyncio.gather(fresh, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize('before_first_turn', [False, True])
def test_cancelled_owner_releases_event_and_cycle_state(monkeypatch, before_first_turn):
    async def scenario():
        cache = setup_cache(monkeypatch)
        started = asyncio.Event()
        late = asyncio.get_running_loop().create_future()

        async def provider(_fn, ticker):
            started.set()
            # Executor work can outlive cancellation of the owner awaiting it.
            await asyncio.shield(late)
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        owner, primary_ready = main._owned_market_now_refresh(force=True)
        if not before_first_turn:
            await asyncio.wait_for(started.wait(), 1)
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
        await asyncio.sleep(0)
        assert primary_ready.is_set()
        assert cache.get('refreshTask') is None
        assert cache.get('primaryReady') is None
        assert cache['scheduled'] is False
        assert cache['refreshing'] is False
        assert not main.MARKET_NOW_LOCK.locked()
        late.set_result(None)
        await asyncio.sleep(0)
        assert cache['data'] is None
        assert cache['timestamp'] == 0.0

    asyncio.run(scenario())


def test_completed_owner_callback_cannot_clear_successor_cycle(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        cache['data'] = {'results': [row(ticker) for ticker in PRIMARY + EXTRAS], 'errors': []}
        cache['timestamp'] = main.time.time()
        started, release = asyncio.Event(), asyncio.Event()
        created = asyncio.get_running_loop().create_future()

        async def provider(_fn, ticker):
            started.set()
            await release.wait()
            return row(ticker)

        monkeypatch.setattr(main, '_background_market_call', provider)
        first, first_ready = main._owned_market_now_refresh(force=True)

        async def successor():
            await first_ready.wait()
            cache['timestamp'] = 0.0
            second, second_ready = main._owned_market_now_refresh(force=True)
            created.set_result((second, second_ready))

        next_cycle = asyncio.create_task(successor())
        second = None
        try:
            second, second_ready = await asyncio.wait_for(created, 1)
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.sleep(0)
            assert second is not first
            assert cache['refreshTask'] is second
            assert cache['primaryReady'] is second_ready
            assert cache['scheduled'] is True
            assert not second.done()
        finally:
            release.set()
            await asyncio.gather(first, next_cycle, *([second] if second else []), return_exceptions=True)

    asyncio.run(scenario())


def test_full_cached_read_keeps_existing_headers_and_has_no_provider_wait(monkeypatch):
    async def scenario():
        cache = setup_cache(monkeypatch)
        cache['data'] = {'results': [row(ticker) for ticker in PRIMARY + EXTRAS], 'errors': []}
        cache['timestamp'] = main.time.time()

        async def forbidden_provider(_fn, _ticker):
            raise AssertionError('fresh full cache must not queue a provider')

        monkeypatch.setattr(main, '_background_market_call', forbidden_provider)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
            response = await client.get('/api/market-now')
        assert response.headers['cache-control'] == 'public, max-age=5, s-maxage=5, stale-while-revalidate=20'
        assert 'market-ready;dur=0.000' in response.headers['server-timing']
        assert response.json()['refreshing'] is False
        assert isinstance(response.json()['cacheAgeSec'], (float, int))
        assert cache.get('refreshTask') is None

    asyncio.run(scenario())
