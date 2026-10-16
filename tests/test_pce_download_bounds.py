"""The official download is bounded before buffering an oversized response."""
import importlib

import pytest


def test_collector_and_helper_share_a_streamed_verified_download(monkeypatch):
    helper = importlib.import_module('scripts.pce_release_data')
    collector = importlib.import_module('scripts.generate_inflation_release_cache')
    calls = []
    class Response:
        headers = {}
        closed = False
        def raise_for_status(self): pass
        @property
        def content(self): pytest.fail('must not buffer response.content')
        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield b'official'
            yield b''
            yield b'-workbook'
        def close(self): self.closed = True
    response = Response()
    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(helper.requests, 'get', fetch)
    assert collector.get_text(helper.WORKBOOK_URL) == b'official-workbook'
    assert response.closed
    assert len(calls) == 1 and calls[0][0] == helper.WORKBOOK_URL
    assert calls[0][1]['stream'] is True and calls[0][1]['timeout'] == 25
    assert calls[0][1].get('verify', True) is True and 'proxies' not in calls[0][1]


@pytest.mark.parametrize('header', [True, False])
def test_download_rejects_excess_size_and_closes_without_consuming_remainder(monkeypatch, header):
    helper = importlib.import_module('scripts.pce_release_data')
    class Response:
        headers = {'Content-Length': str(32 * 1024 * 1024 + 1)} if header else {}
        closed = False
        read = 0
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            for _ in range(514):
                self.read += 1
                yield b'x' * 65536
            pytest.fail('oversized download consumed to the end')
        def close(self): self.closed = True
    response = Response()
    monkeypatch.setattr(helper.requests, 'get', lambda *a, **kw: response)
    with pytest.raises(ValueError, match='size'):
        helper.download_pce_workbook()
    assert response.closed
    assert response.read == (0 if header else 513)
