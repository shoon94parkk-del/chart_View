import json
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
