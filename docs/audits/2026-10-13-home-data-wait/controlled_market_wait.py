"""Same provider-free HTTP harness for base/current handlers; not a production SLA."""
import ast
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
parser.add_argument('--output', type=Path, default=Path.cwd() / 'home-data-wait-evidence')
args = parser.parse_args()
ROOT = args.repo.resolve()
EVIDENCE = args.output.resolve()
EVIDENCE.mkdir(parents=True, exist_ok=True)
BASE = '71cb721375c4598b60897e12d0db04f5a2440fa7'
PRIMARY = ['^KS11', '^KQ11', '^GSPC', '^IXIC']
EXTRAS = ['^TNX', '^VIX', 'CL=F', 'KRW=X']
FUNCTIONS = {'_background_market_call', '_quote_has_value', '_quote_observed_epoch',
             '_quote_can_publish', '_refresh_market_now', '_schedule_market_now_refresh',
             '_owned_market_now_refresh', 'market_now'}

base_source = subprocess.run(['git', 'show', f'{BASE}:main.py'], cwd=ROOT,
                             check=True, capture_output=True, text=True).stdout
current_source = (ROOT/'main.py').read_text()

async def measure(stage, source, scenario):
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTIONS]
    for node in selected:
        node.decorator_list = []
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='fake-market-audit')
    cache = {'data': None, 'timestamp': 0.0, 'refreshing': False, 'scheduled': False}
    held_ticker = '^VIX' if scenario == 'one_extra_held_20s' else '^KS11'
    calls = []

    def provider(ticker):
        calls.append(ticker)
        time.sleep(20.0 if ticker == held_ticker else .003)
        return {'ticker': ticker, 'price': 100.0, 'change': 1.0, 'previousClose': 99.0,
                'asOf': '2026-10-13T01:00:00+00:00', 'sessionDate': '2026-10-13',
                'previousSessionDate': '2026-10-12', 'currency': 'USD', 'source': 'controlled fake canonical provider'}

    ns = {'asyncio': asyncio, 'datetime': datetime, 'timedelta': timedelta, 'timezone': timezone,
          'time': time, 'math': math, 'json': json, 'JSONResponse': JSONResponse,
          'BACKGROUND_MARKET_EXECUTOR': pool, 'MARKET_NOW_CACHE': cache,
          'MARKET_NOW_TICKERS': PRIMARY+EXTRAS, 'MARKET_NOW_PRIMARY_TICKERS': tuple(PRIMARY),
          'MARKET_NOW_TTL': 12, 'MARKET_NOW_REFRESH_GUARD': 5,
          'MARKET_NOW_REFRESH_DELAY_SEC': .75, 'MARKET_NOW_INITIAL_WAIT_SEC': 2.0,
          'MARKET_NOW_LOCK': asyncio.Lock(), 'fetch_quote_snapshot': provider,
          'print': lambda *args, **kwargs: None}
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<selected-real-handler-source>', 'exec'), ns)
    app = FastAPI()
    app.get('/api/market-now')(ns['market_now'])
    started = time.perf_counter()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/market-now')
        response_ms = (time.perf_counter()-started)*1000
        payload = response.json()
        owner = cache.get('refreshTask')
        if owner is not None:
            await asyncio.shield(owner)
        terminal_ms = (time.perf_counter()-started)*1000
    pool.shutdown(wait=True)
    record = {'stage': stage, 'scenario': scenario, 'held_ticker': held_ticker,
              'configured_hold_ms': 20000, 'executor_workers': 2,
              'first_http_return_ms': round(response_ms, 3),
              'first_valid_index_available_in_http_ms': round(response_ms, 3),
              'first_response_primary_tickers': [row['ticker'] for row in payload['results'] if row['ticker'] in PRIMARY],
              'first_response_rows': len(payload['results']), 'first_response_refreshing': payload['refreshing'],
              'first_response_cache_age_sec': payload['cacheAgeSec'],
              'first_response_cache_control': response.headers.get('cache-control'),
              'first_response_server_timing': response.headers.get('server-timing'),
              'all8_terminal_ms': round(terminal_ms, 3),
              'terminal_rows': len(cache['data']['results']), 'provider_calls': len(calls),
              'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
    print(json.dumps(record), flush=True)
    return record

async def main():
    print('Four independent simulated instances share the same harness; each keeps its own two-worker pool.', flush=True)
    records = await asyncio.gather(*[measure(stage, source, scenario)
        for stage, source in [('before', base_source), ('after', current_source)]
        for scenario in ['one_extra_held_20s', 'one_primary_held_20s']])
    report = {'base_sha': BASE, 'kind': 'controlled provider-free HTTP handler experiment',
              'not_production_incident_attribution': True, 'not_latency_sla': True,
              'method': 'Select actual handler/cache functions by AST from base and current source, register an isolated FastAPI route without startup, run one ordinary cold ASGI HTTP request. One chosen fake provider sleeps exactly20s; the others sleep3ms. Real run_in_executor pool remains2 per independent simulated instance. No HTTP to external services or additional provider calls.',
              'records': records}
    (EVIDENCE/'controlled-market-wait-before-after.json').write_text(json.dumps(report, indent=2)+'\n')

asyncio.run(main())
