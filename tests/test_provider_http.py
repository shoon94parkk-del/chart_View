"""Connection reuse must retain HTTP behavior and isolate executor threads."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

import market_service
import provider_http


def close_thread_session():
    session = getattr(provider_http._state, 'session', None)
    if session is not None:
        session.close()
        del provider_http._state.session


@pytest.fixture(autouse=True)
def clean_session():
    close_thread_session()
    yield
    close_thread_session()


@pytest.fixture
def http_server(monkeypatch):
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    seen = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            path = urlsplit(self.path)
            row = {'connection': self.client_address[1], 'path': path.path,
                   'query': parse_qs(path.query), 'headers': dict(self.headers)}
            with lock:
                seen.append(row)
            status = 503 if path.path == '/unavailable' else 200
            body = b'not-json' if path.path == '/malformed' else json.dumps(row).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            if path.path == '/cookie':
                self.send_header('Set-Cookie', 'provider-cookie=local-test; Path=/')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', seen
    finally:
        close_thread_session()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_repeated_requests_reuse_connection_and_preserve_per_call_arguments(http_server):
    base, seen = http_server
    headers = {'User-Agent': 'ChartView-test', 'X-Provider-Request': 'one',
               'Authorization': 'local-test-only'}
    first = provider_http.get(base + '/quote', params={'symbol': '^GSPC'},
                              headers=headers, timeout=(1, 2)).json()
    second = provider_http.get(base + '/quote', params={'symbol': 'NVDA'}, timeout=2).json()
    assert first['connection'] == second['connection']
    assert first['query'] == {'symbol': ['^GSPC']}
    assert second['query'] == {'symbol': ['NVDA']}
    assert first['headers']['User-Agent'] == 'ChartView-test'
    assert first['headers']['Authorization'] == 'local-test-only'
    assert 'Authorization' not in second['headers']
    assert 'X-Provider-Request' not in second['headers']
    assert headers == {'User-Agent': 'ChartView-test', 'X-Provider-Request': 'one',
                       'Authorization': 'local-test-only'}
    assert len(seen) == 2


def test_distinct_executor_threads_have_distinct_sessions_and_connections(http_server):
    base, seen = http_server
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait(timeout=3)
            first = provider_http.get(base + '/quote', timeout=2).json()
            second = provider_http.get(base + '/quote', timeout=2).json()
            return (provider_http._state.session, first['connection'], second['connection'])
        finally:
            close_thread_session()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker)
        second = pool.submit(worker)
        a, b = first.result(timeout=5), second.result(timeout=5)
    assert a[0] is not b[0]
    assert a[1] == a[2]
    assert b[1] == b[2]
    assert a[1] != b[1]
    assert len(seen) == 4


def test_session_cookie_does_not_cross_provider_hosts(http_server):
    base, _ = http_server
    provider_http.get(base + '/cookie', timeout=2)
    same_host = provider_http.get(base + '/quote', timeout=2).json()
    other_host = provider_http.get(base.replace('127.0.0.1', 'localhost') + '/quote', timeout=2).json()
    assert same_host['headers']['Cookie'] == 'provider-cookie=local-test'
    assert 'Cookie' not in other_host['headers']


def test_environment_proxy_and_ca_trust_remain_enabled_without_extra_retries(monkeypatch, tmp_path):
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:3128')
    monkeypatch.setenv('https_proxy', 'http://127.0.0.1:3128')
    monkeypatch.setenv('NO_PROXY', '')
    monkeypatch.setenv('REQUESTS_CA_BUNDLE', '/local-test/ca.pem')
    netrc = tmp_path / 'empty-netrc'
    netrc.write_text('')
    monkeypatch.setenv('NETRC', str(netrc))
    sent = []

    def fake_send(session, request, **kwargs):
        sent.append((request, kwargs))
        response = requests.Response()
        response.status_code = 200
        response._content = b'{}'
        response.url = request.url
        return response

    monkeypatch.setattr(requests.Session, 'send', fake_send)
    provider_http.get('https://provider.example/quote', params={'symbol': 'NVDA'},
                      timeout=(2.5, 4.5))
    session = provider_http._state.session
    assert session.trust_env is True
    assert session.verify is True
    assert session.get_adapter('https://').max_retries.total == 0
    assert len(sent) == 1
    request, settings = sent[0]
    assert request.url == 'https://provider.example/quote?symbol=NVDA'
    assert settings['timeout'] == (2.5, 4.5)
    assert settings['verify'] == '/local-test/ca.pem'
    assert settings['proxies']['https'] == 'http://127.0.0.1:3128'


def test_http_json_keeps_status_failure_and_malformed_body_behavior_without_retry(http_server):
    base, seen = http_server
    with pytest.raises(requests.HTTPError):
        market_service._http_json(base + '/unavailable', timeout=2)
    with pytest.raises(ValueError):
        market_service._http_json(base + '/malformed', timeout=2)
    actual = market_service._http_json(base + '/quote', params={'symbol': '^IXIC'}, timeout=2)
    assert actual['query'] == {'symbol': ['^IXIC']}
    assert actual['headers']['User-Agent'] == market_service.HEADERS['User-Agent']
    assert [row['path'] for row in seen] == ['/unavailable', '/malformed', '/quote']
    assert len({row['connection'] for row in seen}) == 1


def test_transport_timeout_propagates_once_with_original_call_arguments(monkeypatch):
    calls = []
    error = requests.Timeout('local-test timeout')

    def fail(session, url, **kwargs):
        calls.append((url, kwargs))
        raise error

    monkeypatch.setattr(requests.Session, 'get', fail)
    with pytest.raises(requests.Timeout) as caught:
        market_service._http_json('https://provider.example/quote', params={'symbol': 'NVDA'},
                                  timeout=4)
    assert caught.value is error
    assert calls == [('https://provider.example/quote',
                      {'params': {'symbol': 'NVDA'}, 'headers': market_service.HEADERS, 'timeout': 4})]


def test_canonical_quote_keeps_sparse_intraday_daily_fallback_without_transport_retry(monkeypatch):
    calls = []
    chart_rows = [
        {'meta': {'currency': 'USD'}, 'timestamp': [], 'indicators': {'quote': [{'close': []}]}},
        {'meta': {'currency': 'USD', 'exchangeTimezoneName': 'America/New_York'},
         'timestamp': [1791838800, 1791925200],
         'indicators': {'quote': [{'close': [100, 102]}]}},
    ]

    def get(url, **kwargs):
        calls.append((url, kwargs))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({'chart': {'result': [chart_rows[len(calls)-1]]}}).encode()
        response.url = url
        return response

    monkeypatch.setattr(provider_http, 'get', get)
    symbol = 'TEST-PROVIDER-HTTP'
    market_service._quote_cache.pop(symbol, None)
    try:
        row = market_service.fetch_quote_snapshot(symbol)
        assert row['ticker'] == symbol
        assert row['price'] == 102
        assert row['previousClose'] == 100
        assert row['change'] == 2
        assert row['source'] == 'Yahoo Chart daily atomic snapshot'
        assert [kwargs['params']['range'] for _, kwargs in calls] == ['5d', '1mo']
        assert [kwargs['params']['interval'] for _, kwargs in calls] == ['5m', '1d']
        assert all(kwargs['timeout'] == 9.0 and kwargs['headers'] == market_service.HEADERS
                   for _, kwargs in calls)
    finally:
        market_service._quote_cache.pop(symbol, None)
