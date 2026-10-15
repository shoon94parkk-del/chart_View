"""Provider-free runtime regressions for shared per-ticker quote publication.

ASGITransport deliberately runs without lifespan: importing the app must not
start its warmers. Held fake providers exercise response ordering, not latency.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import threading
import time

import httpx
import pytest

import main


HOME_FAST = "005930.KS"
HOME_HELD = "000660.KS"
INDEX_FAST = "^KS11"
INDEX_HELD = "^VIX"


def _quote(ticker, price, as_of):
    return {
        "ticker": ticker,
        "name": ticker,
        "price": price,
        "previousClose": price - 1,
        "change": 1.0,
        "currency": "KRW" if ticker.endswith(".KS") or ticker == INDEX_FAST else "USD",
        "asOf": as_of,
        "sessionDate": as_of[:10],
        "previousSessionDate": "2026-10-12",
        "source": "fake canonical provider",
        "stale": False,
    }


@pytest.fixture
def quote_state(monkeypatch):
    observed = datetime.now(timezone.utc) - timedelta(minutes=2)
    stamps = {
        "old": observed.isoformat(),
        "older": (observed - timedelta(seconds=30)).isoformat(),
        "new": (observed + timedelta(seconds=30)).isoformat(),
        "newest": (observed + timedelta(seconds=60)).isoformat(),
    }
    old_epoch = time.time() - 3600
    home_rows = {
        HOME_FAST: _quote(HOME_FAST, 100, stamps["old"]),
        HOME_HELD: _quote(HOME_HELD, 200, stamps["old"]),
    }
    monkeypatch.setattr(main, "HOME_MAJOR_TICKERS", [HOME_FAST, HOME_HELD])
    monkeypatch.setattr(main, "MARKET_NOW_TICKERS", [INDEX_FAST, INDEX_HELD])
    monkeypatch.setattr(main, "HOME_LIVE_CACHE", {
        "quotes": home_rows,
        "updatedAt": stamps["old"],
        "marketUpdatedAt": {"KR": stamps["old"], "US": None},
        "marketUpdatedEpoch": {"KR": old_epoch, "US": 0.0},
        "quoteUpdatedEpoch": {ticker: old_epoch for ticker in home_rows},
        "refreshing": False,
        "lastError": None,
        "source": "test memory",
    })
    monkeypatch.setattr(main, "MARKET_NOW_CACHE", {
        "data": {
            "results": [
                _quote(INDEX_FAST, 100, stamps["old"]),
                _quote(INDEX_HELD, 200, stamps["old"]),
            ],
            "errors": [],
            "basis": "previous_close",
        },
        # Older than the refresh guard, younger than normal endpoint SWR TTL.
        "timestamp": time.time() - 6,
        "refreshing": False,
        "scheduled": False,
    })
    monkeypatch.setattr(main, "HOME_LIVE_REFRESH_LOCK", asyncio.Lock())
    monkeypatch.setattr(main, "MARKET_NOW_LOCK", asyncio.Lock())
    monkeypatch.setattr(main, "HOME_LIVE_WAKE_EVENT", None)
    monkeypatch.setattr(main, "_open_home_markets", lambda *args: {"KR": [HOME_FAST, HOME_HELD]})

    def forbidden_provider(*args, **kwargs):
        raise AssertionError("a test reached an unconfigured provider")

    async def forbidden_background(*args, **kwargs):
        forbidden_provider()

    monkeypatch.setattr(main, "fetch_quote_snapshot", forbidden_provider)
    monkeypatch.setattr(main, "_background_market_call", forbidden_background)
    monkeypatch.setattr(main.requests.sessions.Session, "request", forbidden_provider)
    return {**stamps, "old_epoch": old_epoch}


async def _settle():
    # Drain ready callbacks; there is no provider timeout or performance SLA.
    for _ in range(12):
        await asyncio.sleep(0)


def _client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    )


async def _payload(client, path, **params):
    response = await asyncio.wait_for(client.get(path, params=params), timeout=1)
    assert response.status_code == 200
    return response.json()


def _rows(payload):
    return {row["ticker"]: row for row in payload["results"]}


async def _finish(task, release):
    release.set()
    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1)


def test_market_now_exposes_completed_index_while_another_provider_is_held(monkeypatch, quote_state):
    async def scenario():
        release, fast_done, held_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def provider(fn, ticker):
            if ticker == INDEX_HELD:
                held_started.set()
                await release.wait()
                return _quote(ticker, 201, quote_state["new"])
            fast_done.set()
            return _quote(ticker, 101, quote_state["new"])

        monkeypatch.setattr(main, "_background_market_call", provider)
        worker = asyncio.create_task(main._refresh_market_now(force=True))
        try:
            await asyncio.wait_for(asyncio.gather(fast_done.wait(), held_started.wait()), 1)
            await _settle()
            async with _client() as client:
                payload = await _payload(client, "/api/market-now")
            assert not worker.done()
            assert payload["refreshing"] is True
            assert _rows(payload)[INDEX_FAST]["price"] == 101
            assert _rows(payload)[INDEX_HELD]["price"] == 200
            assert _rows(payload)[INDEX_FAST]["asOf"] == quote_state["new"]
        finally:
            await _finish(worker, release)

    asyncio.run(scenario())


def test_home_and_normal_quotes_expose_only_completed_ticker_with_its_own_epoch(monkeypatch, quote_state):
    async def scenario():
        release, fast_done, held_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def provider(fn, ticker):
            if ticker == HOME_HELD:
                held_started.set()
                await release.wait()
                return _quote(ticker, 201, quote_state["new"])
            fast_done.set()
            return _quote(ticker, 101, quote_state["new"])

        monkeypatch.setattr(main, "_background_market_call", provider)
        worker = asyncio.create_task(main._refresh_home_live({"KR": [HOME_FAST, HOME_HELD]}))
        try:
            await asyncio.wait_for(asyncio.gather(fast_done.wait(), held_started.wait()), 1)
            await _settle()
            async with _client() as client:
                home = await _payload(client, "/api/home-live")
                assert not worker.done()
                assert home["refreshing"] is True
                assert _rows(home)[HOME_FAST]["price"] == 101
                assert _rows(home)[HOME_HELD]["price"] == 200
                quotes = await _payload(client, "/api/quotes", tickers=HOME_FAST)
                assert _rows(quotes)[HOME_FAST]["price"] == 101
                assert quotes["sharedCacheHits"] == 1
                assert quotes["providerFetches"] == 0
                assert quotes["freshRequested"] is False
            cache = main.HOME_LIVE_CACHE
            assert cache["quoteUpdatedEpoch"][HOME_FAST] > quote_state["old_epoch"]
            assert cache["quoteUpdatedEpoch"][HOME_HELD] == quote_state["old_epoch"]
            assert cache["marketUpdatedEpoch"]["KR"] == quote_state["old_epoch"]
            assert home["marketUpdatedAt"]["KR"] == quote_state["old"]
        finally:
            await _finish(worker, release)
        assert main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][HOME_HELD] > quote_state["old_epoch"]
        assert main.HOME_LIVE_CACHE["marketUpdatedEpoch"]["KR"] > quote_state["old_epoch"]

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["home", "market"])
@pytest.mark.parametrize("bad_result", [
    "older", "unknown_asof", "malformed_asof", "malformed_price", "failure", "empty",
])
def test_unusable_provider_result_preserves_valid_dated_quote(monkeypatch, quote_state, kind, bad_result):
    ticker = HOME_FAST if kind == "home" else INDEX_FAST
    candidate = _quote(ticker, 90, quote_state["new"])
    if bad_result == "older":
        candidate["asOf"] = quote_state["older"]
    elif bad_result == "unknown_asof":
        candidate["asOf"] = None
    elif bad_result == "malformed_asof":
        candidate["asOf"] = "not-an-observation-time"
    elif bad_result == "malformed_price":
        candidate["price"] = "not-a-price"

    async def provider(fn, symbol):
        if bad_result == "failure":
            raise RuntimeError("fake provider unavailable")
        return None if bad_result == "empty" else deepcopy(candidate)

    monkeypatch.setattr(main, "_background_market_call", provider)
    if kind == "market":
        monkeypatch.setattr(main, "MARKET_NOW_TICKERS", [ticker])

    async def scenario():
        if kind == "home":
            await main._refresh_home_live({"KR": [ticker]})
            path = "/api/home-live"
        else:
            await main._refresh_market_now(force=True)
            path = "/api/market-now"
        async with _client() as client:
            row = _rows(await _payload(client, path))[ticker]
        assert row["price"] == 100
        assert row["asOf"] == quote_state["old"]
        if kind == "home":
            assert main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][ticker] == quote_state["old_epoch"]

    asyncio.run(scenario())


@pytest.mark.parametrize("late_asof", ["new", "newest"])
def test_late_home_worker_cannot_undo_newer_foreground_quote(monkeypatch, quote_state, late_asof):
    async def scenario():
        release, started = asyncio.Event(), asyncio.Event()

        async def provider(fn, ticker):
            started.set()
            await release.wait()
            return _quote(ticker, 101, quote_state[late_asof])

        monkeypatch.setattr(main, "_background_market_call", provider)
        monkeypatch.setattr(main, "fetch_quote_snapshot", lambda ticker: _quote(ticker, 105, quote_state["newest"]))
        worker = asyncio.create_task(main._refresh_home_live({"KR": [HOME_FAST]}))
        try:
            await asyncio.wait_for(started.wait(), 1)
            async with _client() as client:
                foreground = await _payload(client, "/api/quotes", tickers=HOME_FAST, fresh="true")
                assert _rows(foreground)[HOME_FAST]["price"] == 105
                assert foreground["freshRequested"] is True
                assert foreground["providerFetches"] == 1
                assert not worker.done()
                foreground_epoch = main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][HOME_FAST]
                await _finish(worker, release)
                home = await _payload(client, "/api/home-live")
                quotes = await _payload(client, "/api/quotes", tickers=HOME_FAST)
            assert _rows(home)[HOME_FAST]["price"] == 105
            assert _rows(home)[HOME_FAST]["asOf"] == quote_state["newest"]
            assert _rows(quotes)[HOME_FAST]["price"] == 105
            assert quotes["providerFetches"] == 0
            assert main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][HOME_FAST] == foreground_epoch
        finally:
            await _finish(worker, release)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["home", "market"])
def test_cancelled_refresh_releases_lock_and_never_publishes_late_provider_result(monkeypatch, quote_state, kind):
    async def scenario():
        ticker = HOME_FAST if kind == "home" else INDEX_FAST
        started = asyncio.Event()
        late_result = asyncio.get_running_loop().create_future()

        async def provider(fn, symbol):
            started.set()
            # Like an executor thread: cancelling the await does not end the work.
            return await asyncio.shield(late_result)

        monkeypatch.setattr(main, "_background_market_call", provider)
        if kind == "market":
            monkeypatch.setattr(main, "MARKET_NOW_TICKERS", [ticker])
        refresh = (lambda: main._refresh_home_live({"KR": [ticker]})) if kind == "home" else (lambda: main._refresh_market_now(force=True))
        cache = main.HOME_LIVE_CACHE if kind == "home" else main.MARKET_NOW_CACHE
        lock = main.HOME_LIVE_REFRESH_LOCK if kind == "home" else main.MARKET_NOW_LOCK
        path = "/api/home-live" if kind == "home" else "/api/market-now"
        worker = asyncio.create_task(refresh())
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert cache["refreshing"] is True
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(worker, 1)
            assert cache["refreshing"] is False
            assert not lock.locked()
            late_result.set_result(_quote(ticker, 101, quote_state["new"]))
            await _settle()
            async with _client() as client:
                row = _rows(await _payload(client, path))[ticker]
            assert row["price"] == 100
            assert row["asOf"] == quote_state["old"]
            if kind == "home":
                assert cache["quoteUpdatedEpoch"][ticker] == quote_state["old_epoch"]

            async def next_provider(fn, symbol):
                return _quote(symbol, 105, quote_state["newest"])

            monkeypatch.setattr(main, "_background_market_call", next_provider)
            await asyncio.wait_for(refresh(), 1)
            async with _client() as client:
                assert _rows(await _payload(client, path))[ticker]["price"] == 105
        finally:
            if not late_result.done():
                late_result.set_result(_quote(ticker, 101, quote_state["new"]))
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())


def test_fresh_quotes_still_wait_for_complete_canonical_batch(monkeypatch, quote_state):
    async def scenario():
        release = threading.Event()
        fast_done, held_started = threading.Event(), threading.Event()

        def provider(ticker):
            if ticker == HOME_HELD:
                held_started.set()
                assert release.wait(2), "test failed to release its fake provider"
                return _quote(ticker, 205, quote_state["newest"])
            fast_done.set()
            return _quote(ticker, 105, quote_state["newest"])

        monkeypatch.setattr(main, "fetch_quote_snapshot", provider)
        async with _client() as client:
            request = asyncio.create_task(client.get("/api/quotes", params={
                "tickers": f"{HOME_FAST},{HOME_HELD}", "fresh": "true",
            }))
            try:
                assert await asyncio.to_thread(fast_done.wait, 1)
                assert await asyncio.to_thread(held_started.wait, 1)
                await _settle()
                assert not request.done()
                release.set()
                response = await asyncio.wait_for(request, 1)
                assert response.status_code == 200
                payload = response.json()
                assert [row["ticker"] for row in payload["results"]] == [HOME_FAST, HOME_HELD]
                assert [row["price"] for row in payload["results"]] == [105, 205]
                assert payload["providerFetches"] == 2
                assert payload["sharedCacheHits"] == 0
                assert payload["freshRequested"] is True
                assert payload["errors"] == []
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 1)

    asyncio.run(scenario())


async def _home_after_quote_publication(client, ticker, price):
    async def published():
        while main.HOME_LIVE_CACHE["quotes"][ticker]["price"] != price:
            await asyncio.sleep(0)

    try:
        # A failure guard, not a provider/UI latency assertion. Read the real
        # Home endpoint afterward so a missing publication fails on its value.
        await asyncio.wait_for(published(), 1)
    except asyncio.TimeoutError:
        pass
    return await _payload(client, "/api/home-live")


@pytest.mark.parametrize("fresh", [False, True])
def test_quotes_publish_completed_home_row_before_sibling_but_return_full_batch(monkeypatch, quote_state, fresh):
    async def scenario():
        release, held_started = threading.Event(), threading.Event()
        calls = []
        non_home = "IBM"
        fast_row = _quote(HOME_FAST, 105, quote_state["new"])

        def provider(ticker):
            calls.append(ticker)
            if ticker == HOME_HELD:
                held_started.set()
                assert release.wait(3), "test failed to release its fake provider"
                return _quote(ticker, 205, quote_state["new"])
            return deepcopy(fast_row) if ticker == HOME_FAST else _quote(ticker, 305, quote_state["new"])

        monkeypatch.setattr(main, "fetch_quote_snapshot", provider)
        async with _client() as client:
            request = asyncio.create_task(client.get("/api/quotes", params={
                "tickers": f"{HOME_HELD},{HOME_FAST.lower()},{non_home},{HOME_HELD}",
                "fresh": str(fresh).lower(),
            }))
            try:
                assert await asyncio.to_thread(held_started.wait, 1)
                home = await _home_after_quote_publication(client, HOME_FAST, 105)
                assert not request.done()
                assert _rows(home)[HOME_FAST] == fast_row
                assert _rows(home)[HOME_HELD]["price"] == 200
                assert _rows(home)[HOME_HELD]["asOf"] == quote_state["old"]
                cache = main.HOME_LIVE_CACHE
                fast_epoch = cache["quoteUpdatedEpoch"][HOME_FAST]
                assert fast_epoch > quote_state["old_epoch"]
                assert cache["quoteUpdatedEpoch"][HOME_HELD] == quote_state["old_epoch"]
                assert cache["marketUpdatedEpoch"]["KR"] == quote_state["old_epoch"]
                assert non_home not in cache["quotes"]

                ordinary = await _payload(client, "/api/quotes", tickers=HOME_FAST)
                assert ordinary["results"] == [fast_row]
                assert ordinary["sharedCacheHits"] == 1
                assert ordinary["providerFetches"] == 0
                release.set()
                response = await asyncio.wait_for(request, 1)
                assert response.status_code == 200
                payload = response.json()
                assert [row["ticker"] for row in payload["results"]] == [HOME_HELD, HOME_FAST, non_home]
                assert [row["price"] for row in payload["results"]] == [205, 105, 305]
                assert payload["results"][1] == fast_row
                assert payload["errors"] == []
                assert payload["sharedCacheHits"] == 0
                assert payload["providerFetches"] == 3
                assert payload["freshRequested"] is fresh
                assert sorted(calls) == sorted([HOME_HELD, HOME_FAST, non_home])
                assert cache["quoteUpdatedEpoch"][HOME_FAST] == fast_epoch
                assert non_home not in cache["quotes"]
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("late_asof", ["new", "newest"])
def test_late_quote_batch_cannot_replace_newer_home_observation(monkeypatch, quote_state, late_asof):
    async def scenario():
        release, held_started = threading.Event(), threading.Event()
        held_calls = []

        def provider(ticker):
            if ticker == HOME_FAST:
                return _quote(ticker, 105, quote_state["new"])
            held_calls.append(ticker)
            if len(held_calls) == 1:
                held_started.set()
                assert release.wait(3), "test failed to release its fake provider"
                return _quote(ticker, 201, quote_state[late_asof])
            return _quote(ticker, 205, quote_state["newest"])

        monkeypatch.setattr(main, "fetch_quote_snapshot", provider)
        async with _client() as client:
            request = asyncio.create_task(client.get("/api/quotes", params={
                "tickers": f"{HOME_FAST},{HOME_HELD}", "fresh": "true",
            }))
            try:
                assert await asyncio.to_thread(held_started.wait, 1)
                home = await _home_after_quote_publication(client, HOME_FAST, 105)
                assert _rows(home)[HOME_FAST]["price"] == 105
                assert not request.done()
                foreground = await _payload(client, "/api/quotes", tickers=HOME_HELD, fresh="true")
                assert _rows(foreground)[HOME_HELD]["price"] == 205
                updated_epoch = main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][HOME_HELD]
                release.set()
                batch = (await asyncio.wait_for(request, 1)).json()
                # The original batch still returns its own canonical result.
                assert _rows(batch)[HOME_HELD]["price"] == 201
                home = await _payload(client, "/api/home-live")
                assert _rows(home)[HOME_HELD]["price"] == 205
                assert _rows(home)[HOME_HELD]["asOf"] == quote_state["newest"]
                assert main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][HOME_HELD] == updated_epoch
                assert held_calls == [HOME_HELD, HOME_HELD]
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("bad_result", [
    "older", "unknown_asof", "malformed_price", "malformed_change", "failure", "empty",
])
def test_quote_batch_does_not_publish_unusable_home_result(monkeypatch, quote_state, bad_result):
    candidate = _quote(HOME_FAST, 90, quote_state["new"])
    if bad_result == "older":
        candidate["asOf"] = quote_state["older"]
    elif bad_result == "unknown_asof":
        candidate["asOf"] = None
    elif bad_result == "malformed_price":
        candidate["price"] = "not-a-price"
    elif bad_result == "malformed_change":
        candidate["change"] = "not-a-change"

    async def scenario():
        release, held_started = threading.Event(), threading.Event()
        calls = []

        def provider(ticker):
            calls.append(ticker)
            if ticker == HOME_HELD:
                held_started.set()
                assert release.wait(3), "test failed to release its fake provider"
                return _quote(ticker, 205, quote_state["new"])
            if bad_result == "failure":
                raise RuntimeError("fake provider unavailable")
            return None if bad_result == "empty" else deepcopy(candidate)

        monkeypatch.setattr(main, "fetch_quote_snapshot", provider)
        async with _client() as client:
            request = asyncio.create_task(client.get("/api/quotes", params={
                "tickers": f"{HOME_FAST},{HOME_HELD}", "fresh": "true",
            }))
            try:
                assert await asyncio.to_thread(held_started.wait, 1)
                old_row = deepcopy(main.HOME_LIVE_CACHE["quotes"][HOME_FAST])
                release.set()
                payload = (await asyncio.wait_for(request, 1)).json()
                home = await _payload(client, "/api/home-live")
                assert _rows(home)[HOME_FAST] == old_row
                assert main.HOME_LIVE_CACHE["quoteUpdatedEpoch"][HOME_FAST] == quote_state["old_epoch"]
                assert payload["providerFetches"] == 2
                assert payload["sharedCacheHits"] == 0
                assert sorted(calls) == sorted([HOME_FAST, HOME_HELD])
                if bad_result in {"failure", "empty"}:
                    assert [row["ticker"] for row in payload["results"]] == [HOME_HELD]
                    expected = "fake provider unavailable" if bad_result == "failure" else "현재 시세를 가져오지 못했습니다."
                    assert payload["errors"] == [{"ticker": HOME_FAST, "message": expected}]
                else:
                    # Preserve the existing HTTP result/error contract even
                    # when the shared Home publisher rejects the candidate.
                    assert payload["results"][0] == candidate
                    assert payload["errors"] == []
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 1)

    asyncio.run(scenario())
