"""Opt-in early news delivery exercises real cache/owner work with held providers."""
import asyncio
from contextlib import suppress
from copy import deepcopy
import threading
import time

from fastapi import FastAPI
import httpx
import pytest

import news_service_v37 as news


def receipt(symbol, *, empty=False, error=None):
    return {
        "items": [] if empty or error else [{
            "symbol": symbol, "title": f"Verified {symbol} earnings",
            "url": f"https://example.com/{symbol}", "score": 70,
            "publishedTs": 100, "investmentRelevant": True,
        }],
        "error": error, "provider": "synthetic",
    }


def seed(symbol, data):
    news.NEWS_CACHE[f"{symbol}|{symbol}"] = {
        "cachedAt": time.time(), "data": deepcopy(data),
    }


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(.001)
    await asyncio.wait_for(wait(), 1)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(news, "NEWS_CACHE", {})
    monkeypatch.setattr(news, "_NEWS_OWNERS", {})
    monkeypatch.setattr(news, "NEWS_RESPONSE_BUDGET", .3)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external provider request")

    monkeypatch.setattr(news.requests.sessions.Session, "request", forbidden)


def client():
    app = FastAPI()
    app.include_router(news.router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def get(client, symbols, **params):
    return await client.get("/api/personalized-news", params={
        "tickers": ",".join(symbols), "names": "|".join(symbols), **params,
    })


def test_cached_group_returns_with_ordered_pending_without_timing_out_owner(monkeypatch):
    seed("AAPL", receipt("AAPL"))
    release = threading.Event()
    calls = []

    def provider(symbol, name):
        calls.append((symbol, name))
        release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        try:
            async with client() as http:
                response = await get(http, ["NVDA", "AAPL"], delivery="first_available")
            body = response.json()
            assert [row["status"] for row in body["groups"]] == ["pending", "success"]
            assert body["groups"][0]["items"] == []
            assert body["groups"][0]["cache"] is None
            assert body["groups"][1]["cache"] == "hit"
            assert body["pendingSymbols"] == ["NVDA"]
            assert body["complete"] is False
            assert body["errors"] == []
            assert response.headers["cache-control"] == "no-store"
            assert "NVDA|NVDA" not in news.NEWS_CACHE
            await until(lambda: len(calls) == 1)
            assert calls == [("NVDA", "NVDA")]
        finally:
            release.set()
            await until(lambda: not news._NEWS_OWNERS)
        assert news.NEWS_CACHE["NVDA|NVDA"]["data"]["error"] is None

    asyncio.run(scenario())


def test_all_misses_deliver_first_completed_group_and_followup_joins_held_owner(monkeypatch):
    release = threading.Event()
    calls = []

    def provider(symbol, name):
        calls.append(symbol)
        if symbol == "NVDA":
            release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        followup = None
        try:
            async with client() as http:
                response = await get(http, ["NVDA", "AAPL"], delivery="first_available")
                body = response.json()
                assert [row["status"] for row in body["groups"]] == ["pending", "success"]
                assert body["pendingSymbols"] == ["NVDA"]
                await until(lambda: calls.count("NVDA") == 1)
                owner = news._NEWS_OWNERS["NVDA|NVDA"]
                followup = asyncio.create_task(get(http, ["NVDA"], delivery="first_available"))
                await asyncio.sleep(.01)
                assert not followup.done()
                assert news._NEWS_OWNERS["NVDA|NVDA"] is owner
                release.set()
                finished = (await followup).json()
                assert finished["pendingSymbols"] == []
                assert finished["complete"] is True
                assert finished["groups"][0]["status"] == "success"
                assert finished["errors"] == []
                assert sorted(calls) == ["AAPL", "NVDA"]
        finally:
            release.set()
            if followup:
                await asyncio.gather(followup, return_exceptions=True)
            await until(lambda: not news._NEWS_OWNERS)

    asyncio.run(scenario())


def test_cancelled_progressive_subscriber_leaves_owner_available_to_other_caller(monkeypatch):
    release = threading.Event()
    started = threading.Event()
    calls = []

    def provider(symbol, name):
        calls.append(symbol)
        started.set()
        release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        second = None
        async with client() as http:
            first = asyncio.create_task(get(http, ["NVDA"], delivery="first_available"))
            try:
                await until(started.is_set)
                owner = news._NEWS_OWNERS["NVDA|NVDA"]
                first.cancel()
                with suppress(asyncio.CancelledError):
                    await first
                assert not owner.cancelled()
                second = asyncio.create_task(get(http, ["NVDA"], delivery="first_available"))
                await asyncio.sleep(.01)
                release.set()
                body = (await second).json()
                assert body["complete"] is True
                assert body["groups"][0]["status"] == "success"
                assert calls == ["NVDA"]
            finally:
                release.set()
                await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
                await until(lambda: not news._NEWS_OWNERS)

    asyncio.run(scenario())


@pytest.mark.parametrize("data,status,errors", [
    (receipt("AAPL", empty=True), "no_news", []),
    (receipt("AAPL", error="provider_error:Timeout"), "error", [
        {"symbol": "AAPL", "provider": "synthetic", "code": "provider_error:Timeout"},
    ]),
])
def test_terminal_empty_and_provider_error_are_not_pending(monkeypatch, data, status, errors):
    seed("AAPL", data)
    release = threading.Event()

    def provider(symbol, name):
        release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        try:
            async with client() as http:
                body = (await get(http, ["AAPL", "NVDA"], delivery="first_available")).json()
            assert [row["status"] for row in body["groups"]] == [status, "pending"]
            assert body["pendingSymbols"] == ["NVDA"]
            assert body["errors"] == errors
        finally:
            release.set()
            await until(lambda: not news._NEWS_OWNERS)

    asyncio.run(scenario())


def test_collection_deadline_still_marks_unfinished_group_as_timeout(monkeypatch):
    monkeypatch.setattr(news, "NEWS_RESPONSE_BUDGET", .02)
    release = threading.Event()

    def provider(symbol, name):
        release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        try:
            async with client() as http:
                body = (await get(http, ["NVDA"], delivery="first_available")).json()
            assert body["groups"][0]["status"] == "error"
            assert body["errors"] == [{"symbol": "NVDA", "provider": "finnhub", "code": "news_timeout"}]
            assert body["pendingSymbols"] == []
            assert body["complete"] is True
            assert "NVDA|NVDA" not in news.NEWS_CACHE
        finally:
            release.set()
            await until(lambda: not news._NEWS_OWNERS)

    asyncio.run(scenario())


def test_progressive_force_reuses_healthy_groups_and_retries_only_cached_error(monkeypatch):
    seed("AAPL", receipt("AAPL"))
    seed("MSFT", receipt("MSFT", empty=True))
    seed("NVDA", receipt("NVDA", error="provider_error:Timeout"))
    release = threading.Event()
    calls = []

    def provider(symbol, name):
        calls.append(symbol)
        release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        try:
            async with client() as http:
                body = (await get(http, ["AAPL", "MSFT", "NVDA"], delivery="first_available", force="true")).json()
            assert [row["status"] for row in body["groups"]] == ["success", "no_news", "pending"]
            assert [row["cache"] for row in body["groups"]] == ["hit", "hit", None]
            assert body["errors"] == []
            assert body["pendingSymbols"] == ["NVDA"]
            await until(lambda: bool(calls))
            assert calls == ["NVDA"]
        finally:
            release.set()
            await until(lambda: not news._NEWS_OWNERS)

    asyncio.run(scenario())


def test_empty_progressive_request_is_complete_and_unknown_delivery_is_rejected():
    async def scenario():
        async with client() as http:
            empty = (await get(http, [], delivery="first_available")).json()
            assert empty["groups"] == []
            assert empty["pendingSymbols"] == []
            assert empty["complete"] is True
            assert (await get(http, [], delivery="invalid")).status_code == 422

    asyncio.run(scenario())


@pytest.mark.parametrize("delivery", [None, "complete"])
def test_default_complete_delivery_keeps_waiting_for_held_sibling(monkeypatch, delivery):
    seed("AAPL", receipt("AAPL"))
    release = threading.Event()
    started = threading.Event()

    def provider(symbol, name):
        started.set()
        release.wait(2)
        return receipt(symbol)

    monkeypatch.setattr(news, "_fetch_finnhub_news", provider)

    async def scenario():
        async with client() as http:
            task = asyncio.create_task(get(http, ["AAPL", "NVDA"], **({"delivery": delivery} if delivery else {})))
            try:
                await until(started.is_set)
                await asyncio.sleep(.01)
                assert not task.done()
                release.set()
                body = (await task).json()
                assert [row["status"] for row in body["groups"]] == ["success", "success"]
                assert "pendingSymbols" not in body
                assert "complete" not in body
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
                await until(lambda: not news._NEWS_OWNERS)

    asyncio.run(scenario())
