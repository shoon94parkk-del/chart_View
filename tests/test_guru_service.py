import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import HTTPException
import guru_service as service


def cache(tmp_path, version='v1'):
    p=tmp_path/'guru_evidence.json'
    p.write_text(json.dumps({'snapshotVersion':version,'companies':{'005930.KS':{'symbol':'005930.KS','annual':[]}}}),encoding='utf-8')
    return p


def test_reads_evidence_without_provider_calls(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'EVIDENCE_PATH',cache(tmp_path))
    with patch('requests.get',side_effect=AssertionError('Unexpected provider I/O')):
        result=service.get_guru_evidence('005930.KS','v1')
    assert result['symbol']=='005930.KS'
    assert result['snapshotVersion']=='v1'


@pytest.mark.parametrize('ticker,version,code',[('005930.KS','old',409),('../unsafe','v1',400),('000001.KS','v1',404)])
def test_invalid_ticker_and_versions_are_explicit(tmp_path,monkeypatch,ticker,version,code):
    monkeypatch.setattr(service,'EVIDENCE_PATH',cache(tmp_path))
    with pytest.raises(HTTPException) as e: service.get_guru_evidence(ticker,version)
    assert e.value.status_code==code


def test_unavailable_cache_503(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'EVIDENCE_PATH',tmp_path/'missing.json')
    with pytest.raises(HTTPException) as e: service.get_guru_evidence('005930.KS','v1')
    assert e.value.status_code==503


def test_cache_replacement_reloads(tmp_path,monkeypatch):
    monkeypatch.setattr(service,'EVIDENCE_PATH',cache(tmp_path))
    assert service.get_guru_evidence('005930.KS','v1')['snapshotVersion']=='v1'
    cache(tmp_path,'v2')
    assert service.get_guru_evidence('005930.KS','v2')['snapshotVersion']=='v2'


@pytest.mark.parametrize('prime_current_version', [False, True])
def test_obsolete_versions_reuse_unchanged_evidence_file(tmp_path, monkeypatch, prime_current_version):
    path = cache(tmp_path)
    monkeypatch.setattr(service, 'EVIDENCE_PATH', path)
    reads = []
    original_read = Path.read_text

    def counted_read(file, *args, **kwargs):
        reads.append(file)
        return original_read(file, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', counted_read)
    if prime_current_version:
        service.get_guru_evidence('005930.KS', 'v1')

    for version in ['old', 'another-old', 'old']:
        with pytest.raises(HTTPException) as error:
            service.get_guru_evidence('005930.KS', version)
        assert error.value.status_code == 409
        assert error.value.detail == {'code': 'snapshot_changed', 'currentVersion': 'v1'}

    assert service.get_guru_evidence('005930.KS', 'v1') == {
        'symbol': '005930.KS', 'annual': [], 'snapshotVersion': 'v1',
        'tradeDate': None, 'criteriaVersion': None,
    }
    assert reads == [path]


def test_atomic_replacement_with_same_size_and_timestamp_reloads(tmp_path, monkeypatch):
    path = cache(tmp_path)
    monkeypatch.setattr(service, 'EVIDENCE_PATH', path)
    assert service.get_guru_evidence('005930.KS', 'v1')['snapshotVersion'] == 'v1'
    old_stat = path.stat()
    replacement = tmp_path / 'replacement.json'
    replacement.write_text(json.dumps({
        'snapshotVersion': 'v2',
        'companies': {'005930.KS': {'symbol': '005930.KS', 'annual': []}},
    }), encoding='utf-8')
    os.utime(replacement, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    replacement.replace(path)
    assert path.stat().st_size == old_stat.st_size
    assert path.stat().st_mtime_ns == old_stat.st_mtime_ns
    assert path.stat().st_ino != old_stat.st_ino

    with pytest.raises(HTTPException) as error:
        service.get_guru_evidence('005930.KS', 'v1')
    assert error.value.status_code == 409
    assert error.value.detail == {'code': 'snapshot_changed', 'currentVersion': 'v2'}
    assert service.get_guru_evidence('005930.KS', 'v2')['snapshotVersion'] == 'v2'


def test_evidence_update_for_same_snapshot_version_reloads(tmp_path, monkeypatch):
    path = cache(tmp_path)
    monkeypatch.setattr(service, 'EVIDENCE_PATH', path)
    assert service.get_guru_evidence('005930.KS', 'v1')['annual'] == []
    path.write_text(json.dumps({
        'snapshotVersion': 'v1',
        'companies': {'005930.KS': {'symbol': '005930.KS', 'annual': [{'year': 2025}]}},
    }), encoding='utf-8')
    assert service.get_guru_evidence('005930.KS', 'v1')['annual'] == [{'year': 2025}]
