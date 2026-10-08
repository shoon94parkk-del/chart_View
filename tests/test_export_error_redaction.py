"""Public/customs diagnostics may never echo provider credentials or URLs."""
import asyncio
import json

import pytest
import requests
from fastapi import HTTPException, Response

import export_momentum_service as service

SECRET = 'not-a-real-secret-for-regression'
RAW = '/provider?serviceKey=' + SECRET + '&month=202609'


def safe(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    assert SECRET not in text
    assert 'serviceKey' not in text
    assert '/provider' not in text


@pytest.mark.parametrize('kind', [requests.ConnectTimeout, requests.ConnectionError, requests.HTTPError, RuntimeError])
def test_provider_errors_never_format_messages_or_custom_exception_strings(kind):
    safe(service._safe_provider_error(kind(RAW)))
    class Unsafe(RuntimeError):
        def __str__(self):
            pytest.fail('Provider exception must never be formatted')
    safe(service._safe_provider_error(Unsafe()))


def test_http_layer_discards_raw_connection_error_and_exception_chain(monkeypatch):
    monkeypatch.setattr(service, 'service_key', lambda: SECRET)
    def fail(*args, **kwargs):
        raise requests.ConnectTimeout(RAW)
    monkeypatch.setattr(service.requests, 'get', fail)
    with pytest.raises(service.CustomsApiError) as error:
        service._request_rows('https://provider.invalid')
    safe(str(error.value))
    assert error.value.__suppress_context__


@pytest.mark.parametrize('xml', [
    '<response><resultCode>99</resultCode><resultMsg>'+RAW.replace('&','&amp;')+'</resultMsg></response>',
    '<response><resultMsg>SERVICE KEY '+SECRET+'</resultMsg></response>',
])
def test_xml_provider_error_body_cannot_be_reflected(xml):
    with pytest.raises(service.CustomsApiError) as error:
        service._parse_xml_payload(xml.encode())
    safe(str(error.value))


CASES = [
    ('export_momentum','_refresh_cache','_CACHE','CUSTOMS_API_UNAVAILABLE'),
    ('export_momentum_map','_refresh_momentum_map','_MOMENTUM_MAP_CACHE','EXPORT_MOMENTUM_MAP_UNAVAILABLE'),
    ('export_momentum_provisional','_refresh_provisional_radar','_PROVISIONAL_CACHE','EXPORT_PROVISIONAL_UNAVAILABLE'),
    ('export_momentum_semiconductor_trends','_refresh_semiconductor_trends','_SEMICONDUCTOR_TREND_CACHE','SEMICONDUCTOR_TRENDS_UNAVAILABLE'),
    ('export_momentum_semiconductor_countries','_refresh_semiconductor_country_matrix','_SEMICONDUCTOR_COUNTRY_CACHE','SEMICONDUCTOR_COUNTRY_UNAVAILABLE'),
    ('export_momentum_item_detail','_refresh_item_detail','_DETAIL_CACHE','EXPORT_ITEM_DETAIL_UNAVAILABLE'),
]


@pytest.mark.parametrize('endpoint,refresh,cache,code', CASES)
def test_public_503_keeps_existing_error_code_without_raw_provider_message(monkeypatch,endpoint,refresh,cache,code):
    async def fail(*args):
        raise requests.ConnectTimeout(RAW)
    monkeypatch.setattr(service, refresh, fail)
    monkeypatch.setattr(service, cache, {} if cache=='_DETAIL_CACHE' else {'data':None,'timestamp':0})
    monkeypatch.setattr(service, 'api_key_configured', lambda: True)
    kwargs = {'key':'semiconductor'} if endpoint=='export_momentum_item_detail' else {}
    with pytest.raises(HTTPException) as error:
        asyncio.run(getattr(service,endpoint)(response=Response(),**kwargs))
    assert error.value.status_code==503
    assert error.value.detail['code']==code
    safe(error.value.detail)


@pytest.mark.parametrize('endpoint,refresh,cache,code', CASES[1:])
def test_stale_fallback_keeps_original_values_dates_and_safe_failure_metadata(monkeypatch,endpoint,refresh,cache,code):
    async def fail(*args):
        raise requests.ConnectTimeout(RAW)
    original={'period':'2026-08','history':[{'exports':100,'balance':-10}], 'meta':{}}
    monkeypatch.setattr(service, refresh, fail)
    cached={'semiconductor':{'data':original,'timestamp':0}} if cache=='_DETAIL_CACHE' else {'data':original,'timestamp':0}
    monkeypatch.setattr(service, cache, cached)
    kwargs = {'key':'semiconductor'} if endpoint=='export_momentum_item_detail' else {}
    result=asyncio.run(getattr(service,endpoint)(response=Response(),**kwargs))
    assert result['period']==original['period'] and result['history']==original['history']
    assert result['meta']['cacheStatus']=='stale-error'
    assert original['meta']=={}
    safe(result['meta'])


def test_cache_refresh_and_background_logger_keep_no_raw_failure(monkeypatch,capsys):
    monkeypatch.setattr(service,'_CACHE',{'data':None,'timestamp':0,'refreshing':False})
    monkeypatch.setattr(service,'_CACHE_LOCK',asyncio.Lock())
    def fail():
        raise requests.ConnectTimeout(RAW)
    monkeypatch.setattr(service,'_build_snapshot',fail)
    asyncio.run(service._background_refresh())
    safe(service._CACHE)
    safe(capsys.readouterr().out)
    assert not service._CACHE['refreshing']
    # Old error strings cannot be reflected by the main stale cache metadata.
    service._CACHE['lastError']=RAW
    safe(service._with_cache_meta({'period':'2026-08'},'stale-revalidating'))
