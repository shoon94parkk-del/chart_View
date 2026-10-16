"""Local before/after ASGI comparison. Synthetic providers, never production data."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent
BASE = "a406a4c074a086017363e2c99d677488ce8da55d"
REPO = Path("/workspace/chartview-news-response-budget-20261016")
baseline = ROOT / "news-budget-baseline-source.py"
baseline.write_bytes(subprocess.check_output(["git", "show", f"{BASE}:news_service_v37.py"], cwd=REPO))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def data(symbol):
    return {"items": [{"symbol": symbol, "name": symbol, "market": "US", "title": f"{symbol} simulated earnings", "url": f"https://example.invalid/{symbol}", "score": 60, "publishedTs": time.time(), "investmentRelevant": True}], "error": None, "provider": "simulated-local-only"}

async def measure(module, kind):
    app = FastAPI(); app.include_router(module.router)
    module.NEWS_CACHE.clear()
    calls = {}
    done = threading.Event()
    def provider(symbol, name):
        calls[symbol] = calls.get(symbol, 0) + 1
        if symbol == "SLOW":
            time.sleep(12)  # Deliberate identical provider delay in this local fixture only.
            done.set()
        return data(symbol)
    module._fetch_finnhub_news = provider
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://news-budget.local-test") as client:
        if kind == "occupied-executor-cache":
            loop = asyncio.get_running_loop()
            loop.set_default_executor(ThreadPoolExecutor(max_workers=2))
            started = [asyncio.Event(), asyncio.Event()]
            release = threading.Event()
            def occupy(index):
                loop.call_soon_threadsafe(started[index].set)
                release.wait(2)
            owners = [loop.run_in_executor(None, occupy, i) for i in range(2)]
            await asyncio.gather(*(event.wait() for event in started))
            module.NEWS_CACHE["FAST|FAST"] = {"cachedAt": time.time(), "data": data("FAST")}
            timer = threading.Timer(.25, release.set); timer.start()
            try:
                at = time.perf_counter()
                response = await client.get("/api/personalized-news", params={"tickers": "FAST", "names": "FAST"})
                elapsed = (time.perf_counter() - at) * 1000
            finally:
                release.set(); timer.cancel(); await asyncio.gather(*owners)
            assert response.status_code == 200
            payload = response.json()
            assert payload["groups"][0]["cache"] == "hit" and not calls
            return {"elapsedMs": round(elapsed, 3), "providerCalls": 0, "groups": [{k: row[k] for k in ("symbol", "status", "cache")} for row in payload["groups"]]}
        at = time.perf_counter()
        response = await client.get("/api/personalized-news", params={"tickers": "FAST,SLOW", "names": "FAST|SLOW"})
        elapsed = (time.perf_counter() - at) * 1000
        assert response.status_code == 200
        payload = response.json()
        timeout_cache_written = bool(module.NEWS_CACHE.get("SLOW|SLOW", {}).get("data", {}).get("error"))
        assert not timeout_cache_written
        await asyncio.wait_for(asyncio.to_thread(done.wait, 14), 15)
        follow = await client.get("/api/personalized-news", params={"tickers": "SLOW", "names": "SLOW"})
        assert follow.status_code == 200 and follow.json()["groups"][0]["status"] == "success"
        assert calls == {"FAST": 1, "SLOW": 1}, calls
        return {"elapsedMs": round(elapsed, 3), "groups": [{k: row[k] for k in ("symbol", "status", "cache")} for row in payload["groups"]], "errors": payload["errors"], "timeoutPlaceholderCached": timeout_cache_written, "lateRealResultSuccess": True, "providerCalls": calls}

result = {"method": "In-process httpx ASGI HTTP requests with identical synthetic providers. Not production timing or provider speed.", "baseline": BASE, "afterWorkingTree": str(REPO), "sourceSha256": {"before": hashlib.sha256(baseline.read_bytes()).hexdigest(), "after": hashlib.sha256((REPO / "news_service_v37.py").read_bytes()).hexdigest()}, "conditions": {"slowProviderSeconds": 12, "occupiedDefaultExecutorWorkers": 2, "executorReleaseSeconds": .25}, "samples": {}}
for label, path in [("before", baseline), ("after", REPO / "news_service_v37.py")]:
    result["samples"][label] = {}
    for kind in ["occupied-executor-cache", "slow-provider-partial"]:
        module = load(f"benchmark_{label}_{kind.replace('-', '_')}", path)
        result["samples"][label][kind] = asyncio.run(measure(module, kind))
(ROOT / "news-budget-benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
