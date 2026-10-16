"""Synthetic held-provider regressions for public news collection ownership."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from copy import deepcopy
import threading
import time

import pytest

import news_service_v37 as news


def article(symbol, title='Verified provider headline'):
    return {'symbol':symbol,'title':title,'url':f'https://example.com/{symbol}',
            'score':70,'publishedTs':100,'investmentRelevant':True}


def result(symbol, *, empty=False):
    return {'items':[] if empty else [article(symbol)],'error':None,'provider':'synthetic'}


def seed(symbol, name, data):
    news.NEWS_CACHE[f'{symbol}|{name}'.upper()] = {'cachedAt':time.time(),'data':deepcopy(data)}


async def until(predicate, timeout=1):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail('synthetic worker did not reach the expected state')
        await asyncio.sleep(.001)


@pytest.fixture(autouse=True)
def isolated_news(monkeypatch):
    monkeypatch.setattr(news, 'NEWS_CACHE', {})
    monkeypatch.setattr(news, '_NEWS_OWNERS', {}, raising=False)
    monkeypatch.setattr(news, 'NEWS_RESPONSE_BUDGET', .03, raising=False)
    monkeypatch.setattr(news, 'NEWS_OWNER_LIMIT', 64, raising=False)


def test_fresh_cache_bypasses_saturated_default_executor(monkeypatch):
    seed('NVDA','NVIDIA', result('NVDA'))
    seed('MSFT','Microsoft', result('MSFT',empty=True))
    release, started = threading.Event(), threading.Event()
    def occupied():
        started.set()
        release.wait(2)
    def forbidden(*args, **kwargs):
        pytest.fail('healthy cache must not call a provider')
    monkeypatch.setattr(news, '_fetch_finnhub_news', forbidden)
    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        blocker = loop.run_in_executor(None, occupied)
        await until(started.is_set)
        try:
            payload = await asyncio.wait_for(news.personalized_news(tickers='NVDA,MSFT',names='NVIDIA|Microsoft',force=True), .15)
            assert [(r['status'],r['cache']) for r in payload['groups']] == [('success','hit'),('no_news','hit')]
            assert payload['errors'] == []
        finally:
            release.set()
            await blocker
    asyncio.run(scenario())


def test_absolute_budget_keeps_completed_groups_and_late_real_cache_without_false_empty(monkeypatch):
    release, started = threading.Event(), threading.Event()
    calls = []
    def provider(symbol, name):
        calls.append(symbol)
        if symbol == 'NVDA':
            started.set()
            release.wait(2)
        return result(symbol,empty=symbol == 'MSFT')
    monkeypatch.setattr(news, '_fetch_finnhub_news', provider)
    async def scenario():
        try:
            payload = await asyncio.wait_for(news.personalized_news(tickers='AAPL,NVDA,MSFT',names='Apple|NVIDIA|Microsoft'), .2)
            assert [(r['symbol'],r['status']) for r in payload['groups']] == [('AAPL','success'),('NVDA','error'),('MSFT','no_news')]
            assert payload['errors'] == [{'symbol':'NVDA','provider':'finnhub','code':'news_timeout'}]
            assert payload['groups'][0]['items'] == [article('AAPL')]
            assert payload['groups'][1]['items'] == []
            assert 'NVDA|NVIDIA' not in news.NEWS_CACHE
            retried = await asyncio.wait_for(news.personalized_news(tickers='NVDA',names='NVIDIA',force=True), .2)
            assert retried['errors'][0]['code'] == 'news_timeout'
            assert calls.count('NVDA') == 1
        finally:
            release.set()
        await until(lambda:'NVDA|NVIDIA' in news.NEWS_CACHE)
        recovered = await news.personalized_news(tickers='NVDA',names='NVIDIA')
        assert recovered['errors'] == []
        assert recovered['groups'][0]['status'] == 'success'
        assert recovered['groups'][0]['cache'] == 'hit'
        assert recovered['groups'][0]['items'] == [article('NVDA')]
        assert news.NEWS_CACHE['NVDA|NVIDIA']['data']['error'] is None
    asyncio.run(scenario())


def test_concurrent_normalized_key_callers_share_acquisition_and_cancel_independently(monkeypatch):
    release, started = threading.Event(), threading.Event()
    calls = []
    def provider(symbol, name):
        calls.append((symbol,name))
        started.set()
        release.wait(2)
        return result(symbol)
    monkeypatch.setattr(news,'_fetch_finnhub_news',provider)
    monkeypatch.setattr(news,'NEWS_RESPONSE_BUDGET',1)
    async def scenario():
        first = asyncio.create_task(news.personalized_news(tickers='NVDA',names='NVIDIA'))
        second = None
        try:
            await until(started.is_set)
            second = asyncio.create_task(news.personalized_news(tickers='nvda',names='nvidia',force=True))
            await asyncio.sleep(.02)
            first.cancel()
            with suppress(asyncio.CancelledError):
                await first
            release.set()
            payload = await asyncio.wait_for(second,.5)
            assert payload['errors'] == []
            assert payload['groups'][0]['items'] == [article('NVDA')]
            assert calls == [('NVDA','NVIDIA')]
        finally:
            release.set()
            if second:
                await asyncio.gather(second,return_exceptions=True)
    asyncio.run(scenario())


def test_bounded_owners_include_queued_work_and_allow_healthy_cache_when_full(monkeypatch):
    release, occupied = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(news,'NEWS_OWNER_LIMIT',2)
    seed('MSFT','Microsoft',result('MSFT',empty=True))
    def provider(symbol,name):
        calls.append(symbol)
        release.wait(2)
        return result(symbol)
    monkeypatch.setattr(news,'_fetch_finnhub_news',provider)
    def blocker():
        occupied.set()
        release.wait(2)
    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        held = loop.run_in_executor(None, blocker)
        await until(occupied.is_set)
        try:
            payload = await asyncio.wait_for(news.personalized_news(tickers='AAPL,NVDA,META,MSFT',names='Apple|NVIDIA|Meta|Microsoft'),.2)
            assert [(r['symbol'],r['status']) for r in payload['groups']] == [('AAPL','error'),('NVDA','error'),('META','error'),('MSFT','no_news')]
            assert {r['symbol']:r['code'] for r in payload['errors']} == {'AAPL':'news_timeout','NVDA':'news_timeout','META':'news_busy'}
            assert len(news._NEWS_OWNERS) == 2
            assert calls == []  # Queued owners count against the same bound.
            more = await news.personalized_news(tickers='META,MSFT',names='Meta|Microsoft',force=True)
            assert more['errors'] == [{'symbol':'META','provider':'finnhub','code':'news_busy'}]
            assert more['groups'][1]['cache'] == 'hit'
            assert len(news._NEWS_OWNERS) == 2
        finally:
            release.set()
        await held
        await until(lambda:not news._NEWS_OWNERS)
        assert set(news.NEWS_CACHE) == {'AAPL|APPLE','NVDA|NVIDIA','MSFT|MICROSOFT'}
    asyncio.run(scenario())


def test_completed_owner_releases_capacity_and_later_retry_can_acquire(monkeypatch):
    monkeypatch.setattr(news,'NEWS_OWNER_LIMIT',1)
    calls = []
    def provider(symbol,name):
        calls.append(symbol)
        return result(symbol)
    monkeypatch.setattr(news,'_fetch_finnhub_news',provider)
    async def scenario():
        first = await news.personalized_news(tickers='AAPL',names='Apple')
        assert first['errors'] == []
        await until(lambda:not news._NEWS_OWNERS)
        second = await news.personalized_news(tickers='NVDA',names='NVIDIA')
        assert second['errors'] == []
        assert calls == ['AAPL','NVDA']
    asyncio.run(scenario())


def test_late_ordinary_owner_cannot_overwrite_newer_internal_force_result(monkeypatch):
    release, started = threading.Event(), threading.Event()
    calls = []
    def provider(symbol,name):
        calls.append(symbol)
        if len(calls) == 1:
            started.set()
            release.wait(2)
            return {'items':[article(symbol,'Older result')],'error':None,'provider':'synthetic'}
        return {'items':[article(symbol,'New forced result')],'error':None,'provider':'synthetic'}
    monkeypatch.setattr(news,'_fetch_finnhub_news',provider)
    async def scenario():
        task = asyncio.create_task(news.personalized_news(tickers='NVDA',names='NVIDIA'))
        try:
            await until(started.is_set)
            newer = await asyncio.to_thread(news._cached_fetch,'NVDA','NVIDIA',force=True)
            assert newer['items'][0]['title'] == 'New forced result'
        finally:
            release.set()
        await task
        await until(lambda:not news._NEWS_OWNERS)
        assert news.NEWS_CACHE['NVDA|NVIDIA']['data']['items'][0]['title'] == 'New forced result'
    asyncio.run(scenario())


@pytest.mark.parametrize('cached', [
    {'cachedAt':'broken','data':{}}, {'cachedAt':time.time(),'data':[]},
    {'cachedAt':time.time(),'data':{'items':'invalid','error':None}},
    {'cachedAt':float('nan'),'data':{'items':[],'error':None}},
])
def test_malformed_cache_cannot_break_public_collection_or_fake_no_news(monkeypatch,cached):
    news.NEWS_CACHE['NVDA|NVIDIA'] = cached
    monkeypatch.setattr(news,'_fetch_finnhub_news',lambda symbol,name:result(symbol))
    payload = asyncio.run(news.personalized_news(tickers='NVDA',names='NVIDIA'))
    assert payload['errors'] == []
    assert payload['groups'][0]['items'] == [article('NVDA')]


@pytest.mark.parametrize('data',[None,{'items':'invalid','error':None},{'items':[None],'error':None}])
def test_malformed_worker_result_is_honest_error_not_false_empty(monkeypatch,data):
    monkeypatch.setattr(news,'_fetch_finnhub_news',lambda *args:data)
    payload = asyncio.run(news.personalized_news(tickers='NVDA',names='NVIDIA'))
    assert payload['groups'][0]['status'] == 'error'
    assert payload['groups'][0]['items'] == []
    assert payload['errors'][0]['code'] == 'provider_error:InvalidResponse'


def test_owner_can_be_shared_across_distinct_event_loops(monkeypatch):
    release, started, joined = threading.Event(), threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(news,'NEWS_RESPONSE_BUDGET',1)
    def provider(symbol,name):
        calls.append((symbol,name))
        started.set()
        release.wait(2)
        return result(symbol)
    monkeypatch.setattr(news,'_fetch_finnhub_news',provider)
    async def caller(name):
        if name == 'nvidia':
            joined.set()
        return await news.personalized_news(tickers='NVDA',names=name)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(asyncio.run,caller('NVIDIA'))
        try:
            assert started.wait(1)
            second = callers.submit(asyncio.run,caller('nvidia'))
            assert joined.wait(1)
            time.sleep(.02)
        finally:
            release.set()
        assert first.result(1)['errors'] == second.result(1)['errors'] == []
    assert calls == [('NVDA','NVIDIA')]


def test_concurrent_internal_forces_return_their_own_results_without_cache_rollback(monkeypatch):
    release, started = threading.Event(), threading.Event()
    calls = []
    def provider(symbol,name):
        calls.append(symbol)
        if len(calls) == 1:
            started.set()
            release.wait(2)
            return {'items':[article(symbol,'First internal result')],'error':None,'provider':'synthetic'}
        return {'items':[article(symbol,'Second internal result')],'error':None,'provider':'synthetic'}
    monkeypatch.setattr(news,'_fetch_finnhub_news',provider)
    with ThreadPoolExecutor(max_workers=1) as callers:
        first = callers.submit(news._cached_fetch,'NVDA','NVIDIA',force=True)
        try:
            assert started.wait(1)
            second = news._cached_fetch('NVDA','NVIDIA',force=True)
        finally:
            release.set()
        first_result = first.result(1)
    assert first_result['items'][0]['title'] == 'First internal result'
    assert second['items'][0]['title'] == 'Second internal result'
    assert first_result['cache'] == second['cache'] == 'miss'
    assert news.NEWS_CACHE['NVDA|NVIDIA']['data']['items'][0]['title'] == 'Second internal result'
