"""Offline public news projection, API and publication contracts."""
import copy
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import published_data
from test_published_data import _Response


def sample():
    return {
        "schemaVersion": "investment-news.v1", "generated_at": "2026-10-21T01:00:00Z",
        "as_of_date": "2026-10-21", "status": "PARTIAL",
        "collection": {"status": "PARTIAL", "sources_total": 2, "sources_ok": 1,
                       "last_success_at": "2026-10-21T00:59:00Z", "last_error_at": None},
        "capabilities": {"ai_analysis": False, "telegram_delivery": False},
        "events": [{"event_id": "release-1", "revision": 2, "title": "공식 매출 12% 증가 발표",
                    "published_at": "2026-10-21T00:00:00Z", "first_seen_at": "2026-10-21T00:01:00Z",
                    "updated_at": "2026-10-21T00:59:00Z", "summary": ["공식 자료의 수치 변경을 확인했습니다."],
                    "importance": 82, "confidence": 74, "novelty": 90, "market_impact": 65,
                    "sectors": ["semiconductor"], "tickers": [{"symbol": "NVDA", "name": "NVIDIA", "market": "US"}],
                    "sentiment": "mixed", "facts": [{"text": "매출은 12% 증가했습니다.", "source_url": "https://nvidianews.nvidia.com/news/release",
                                                     "verification": "official_source", "numbers": ["12%"]}],
                    "inferences": [{"text": "후속 수요 확인이 필요합니다.", "condition": "수요가 지속되는 경우", "horizon": "medium"}],
                    "sources": [{"name": "NVIDIA", "url": "https://nvidianews.nvidia.com/news/release", "published_at": "2026-10-21T00:00:00Z",
                                 "retrieved_at": "2026-10-21T00:59:00Z", "kind": "official", "independent_group": "nvidia"}],
                    "verification_status": "official_source", "expectation_status": "unknown", "thesis_status": "no_context",
                    "thesis_reviews": [], "analysis_status": "rules_only", "agents": {},
                    "trade_action": "REVIEW_ONLY", "performance": []}],
        "briefings": [],
    }


def project(doc):
    from intelligence_news_service import public_news
    return public_news(doc)


def test_public_contract_keeps_evidence_scores_revision_and_no_trade_action():
    doc = sample()
    out = project(doc)
    assert out == doc
    assert doc == sample(), "projection must not mutate its input"
    assert out['events'][0]['trade_action'] == 'REVIEW_ONLY'


def test_optional_analysis_fields_are_safe_when_missing():
    doc = sample()
    for key in ('summary', 'facts', 'inferences', 'thesis_reviews', 'agents', 'performance', 'analysis_status', 'expectation_status', 'thesis_status'):
        doc['events'][0].pop(key)
    out = project(doc)['events'][0]
    assert out['agents'] == {} and out['performance'] == []
    assert out['analysis_status'] == 'unavailable'
    assert out['expectation_status'] == 'unknown'
    assert out['thesis_status'] == 'no_context'


def test_real_producer_nested_fields_survive_the_public_projection():
    doc = sample(); event = doc['events'][0]
    doc['collection'] = {'last_success_at': '2026-10-21T00:59:00Z', 'total_sources': 2, 'successful_sources': 1,
                         'sources': [{'source_id': 'nvidia', 'last_success_at': '2026-10-21T00:59:00Z', 'last_attempt_at': '2026-10-21T00:59:00Z', 'count': 1, 'error': None}], 'errors': []}
    doc['capabilities'] = {'ai_configured': True, 'telegram_configured': False, 'telegram_input_enabled': False}
    event['agents'] = {'mer': {'role': 'mer', 'summary': '추가 확인이 필요합니다.', 'direction': 'mixed', 'input_digest': 'abc',
                               'evidence_ids': ['E1'], 'invalidators': ['수요가 감소하는 경우'], 'unknowns': ['시장 기대 미확인'],
                               'inferences': [{'text': '수요 관찰', 'condition': '성장 지속 시', 'horizon': 'medium', 'evidence_ids': ['E1']}]}}
    event['thesis_reviews'] = [{'ticker': 'NVDA', 'thesis_id': 'public-id', 'status': 'review_required', 'reason': '관련 중요 사건 발생: 기존 가설 재검토 필요'}]
    event['performance'] = [{'ticker': 'NVDA', 'baseline_at': '2026-10-20T00:00:00Z', 'followup_at': '2026-10-21T00:00:00Z',
                             'stock_return': None, 'benchmark_return': None, 'excess_return': None, 'source_urls': ['https://nvidianews.nvidia.com/news/release']}]
    doc['briefings'] = [{'date': '2026-10-21', 'generated_at': doc['generated_at'], 'event_ids': ['release-1'], 'newly_confirmed': ['release-1'],
                         'changed_since_previous': [{'event_id': 'release-1', 'revision': 2}],
                         'connections': [{'sector': 'semiconductor', 'event_ids': ['release-1'], 'text': '추가 검증 필요', 'verification': 'inference'}],
                         'coverage_note': '확인된 자료만 표시합니다.', 'trade_action': 'REVIEW_ONLY'}]
    assert project(doc) == doc


def test_utc_publication_and_completed_three_roles_are_required():
    doc = sample(); doc['generated_at'] = '2026-10-21T10:00:00+09:00'
    with pytest.raises(ValueError): project(doc)
    doc = sample(); doc['events'][0]['analysis_status'] = 'completed'
    with pytest.raises(ValueError): project(doc)


def test_briefing_requires_safe_event_ids_and_review_only():
    doc = sample(); doc['briefings'] = [{'date': '2026-10-21', 'generated_at': doc['generated_at'], 'event_ids': ['../invalid'], 'trade_action': 'REVIEW_ONLY'}]
    with pytest.raises(ValueError): project(doc)


def test_historical_briefing_can_reference_an_event_outside_current_retention_window():
    doc = sample(); doc['briefings'] = [{'date': '2026-10-20', 'generated_at': '2026-10-20T12:00:00Z', 'event_ids': ['historical-event'], 'trade_action': 'REVIEW_ONLY'}]
    assert project(doc)['briefings'] == doc['briefings']


def test_actual_collection_failure_rows_remain_visible_without_disclosing_raw_errors():
    doc = sample(); doc['collection'] = {'status': 'PARTIAL', 'failed_sources': 1, 'last_failure_at': '2026-10-21T00:59:00Z',
                                         'sources': [{'source_id': 'nvidia', 'last_failure_at': '2026-10-21T00:59:00Z', 'last_error': 'TimeoutError', 'last_count': 0, 'consecutive_failures': 1}],
                                         'errors': [{'source_id': 'nvidia', 'error': 'TimeoutError'}]}
    assert project(doc)['collection'] == doc['collection']


def test_capability_flags_are_boolean_and_telegram_input_stays_disabled():
    for value in ('yes', 1, True):
        doc = sample(); doc['capabilities'] = {'telegram_input_enabled': value}
        with pytest.raises(ValueError): project(doc)


@pytest.mark.parametrize('field,value', [('summary', True), ('evidence_ids', True), ('unknowns', ['x' * 601])])
def test_agent_result_types_are_not_interpreted_as_success(field, value):
    doc = sample(); doc['events'][0]['agents'] = {'mer': {field: value}}
    with pytest.raises(ValueError): project(doc)


@pytest.mark.parametrize('returns,baseline,followup', [(True, '2026-10-20T00:00:00Z', '2026-10-21T00:00:00Z'),
                                                    (1.2, '2026-10-21T00:00:00Z', '2026-10-20T00:00:00Z'),
                                                    ('1.2', '2026-10-20T00:00:00Z', '2026-10-21T00:00:00Z')])
def test_invalid_return_numbers_and_reversed_observation_windows_are_refused(returns, baseline, followup):
    doc = sample(); doc['events'][0]['performance'] = [{'ticker': 'NVDA', 'baseline_at': baseline, 'followup_at': followup,
                                                     'stock_return': returns, 'source_urls': ['https://example.com/observed-close']}]
    with pytest.raises(ValueError): project(doc)


@pytest.mark.parametrize('field', ['return_pct', 'benchmark_return_pct', 'excess_return_pct', 'mdd_pct'])
def test_unsupported_percentage_aliases_cannot_bypass_observed_return_evidence(field):
    doc = sample()
    doc['events'][0]['performance'] = [{'ticker': 'NVDA', field: 20.0}]
    with pytest.raises(ValueError): project(doc)


@pytest.mark.parametrize('field', ['source_url', 'benchmark_source_url'])
@pytest.mark.parametrize('url', ['file:///srv/private/prices.csv', 'https://t.me/private/1', 'https://example.com/price?token=x'])
def test_scalar_performance_sources_use_the_public_url_guard(field, url):
    doc = sample()
    doc['events'][0]['performance'] = [{'ticker': 'NVDA', field: url}]
    with pytest.raises(ValueError): project(doc)


def test_thesis_review_evidence_urls_use_the_public_url_guard():
    doc = sample()
    doc['events'][0]['thesis_reviews'] = [{'status': 'review_required', 'evidence_urls': ['file:///srv/private/thesis.md']}]
    with pytest.raises(ValueError): project(doc)


def test_safe_scalar_performance_and_thesis_sources_are_preserved():
    doc = sample()
    url = 'https://finance.yahoo.com/quote/NVDA/history/'
    doc['events'][0]['performance'] = [{'ticker': 'NVDA', 'source_url': url, 'benchmark_source_url': url}]
    doc['events'][0]['thesis_reviews'] = [{'status': 'review_required', 'evidence_urls': [url]}]
    assert project(doc) == doc


def test_publication_as_of_date_must_match_the_actual_kst_day():
    doc = sample()
    doc['generated_at'] = '2026-10-20T15:00:00Z'
    doc['as_of_date'] = '2026-10-20'
    with pytest.raises(ValueError): project(doc)


@pytest.mark.parametrize('generated,as_of', [('2026-10-20T14:59:59Z', '2026-10-20'), ('2026-10-20T15:00:00Z', '2026-10-21')])
def test_publication_as_of_date_preserves_both_sides_of_kst_midnight(generated, as_of):
    doc = sample(); doc['generated_at'] = generated; doc['as_of_date'] = as_of
    assert project(doc)['as_of_date'] == as_of


@pytest.mark.parametrize('field', ['telegram_input', 'telegram_input_enabled'])
def test_every_public_telegram_input_alias_remains_disabled(field):
    doc = sample(); doc['capabilities'] = {field: True}
    with pytest.raises(ValueError): project(doc)
    doc['capabilities'][field] = False
    assert project(doc)['capabilities'] == {field: False}


@pytest.mark.parametrize('change', ['schema', 'score', 'action', 'future', 'date', 'duplicate', 'citation', 'telegram', 'credential_url'])
def test_malformed_or_unsafe_news_is_refused(change):
    doc = sample(); event = doc['events'][0]
    if change == 'schema': doc['schemaVersion'] = 'other.v1'
    if change == 'score': event['importance'] = True
    if change == 'action': event['trade_action'] = 'BUY'
    if change == 'future': doc['generated_at'] = '2099-01-01T00:00:00Z'
    if change == 'date': doc['as_of_date'] = '2026-02-30'
    if change == 'duplicate': doc['events'].append(copy.deepcopy(event))
    if change == 'citation': event['facts'][0]['source_url'] = 'https://unrelated.example/fake'
    if change == 'telegram': event['sources'][0]['url'] = 'https://t.me/channel/123'
    if change == 'credential_url': event['sources'][0]['url'] = 'https://user:password@example.com/item'
    with pytest.raises(ValueError): project(doc)


@pytest.mark.parametrize('field,value', [('chat_id', '123'), ('holdings', []), ('raw_text', 'full private article'), ('api_key', 'hidden')])
def test_private_keys_fail_closed_even_when_not_allowlisted(field, value):
    doc = sample(); doc['events'][0][field] = value
    with pytest.raises(ValueError): project(doc)


def test_private_free_text_is_refused_and_unknown_public_metadata_is_dropped():
    doc = sample(); doc['events'][0]['summary'] = ['현재 보유 300주']
    with pytest.raises(ValueError): project(doc)
    doc = sample(); doc['diagnostic'] = 'producer-local'; doc['events'][0]['internal_note'] = 'not for browser'
    out = project(doc)
    assert 'diagnostic' not in out and 'internal_note' not in out['events'][0]


def test_official_sk_company_url_slug_is_not_mistaken_for_an_api_key():
    doc = sample(); url = 'https://news.samsung.com/global/sk-telecom-and-hana-financial-group-buildkoreas-first-ai-data-center'
    doc['events'][0]['sources'][0]['url'] = doc['events'][0]['facts'][0]['source_url'] = url
    assert project(doc)['events'][0]['sources'][0]['url'] == url


@pytest.mark.parametrize('value', ['sk-' + 'a' * 32, 'sk-proj-' + 'a-b_' * 10, 'sk-svcacct-' + 'a-b_' * 10])
def test_genuine_token_shapes_still_fail_the_news_privacy_guard(value):
    doc = sample(); doc['events'][0]['summary'] = [value]
    with pytest.raises(ValueError): project(doc)


def test_credential_query_parameter_is_not_a_public_source_link():
    doc = sample(); url = 'https://example.com/release?access_token=value'
    doc['events'][0]['sources'][0]['url'] = doc['events'][0]['facts'][0]['source_url'] = url
    with pytest.raises(ValueError): project(doc)


def test_long_official_numeric_receipts_are_kept_within_the_document_bound():
    doc = sample(); doc['events'][0]['facts'][0]['numbers'] = [str(n) for n in range(66)]
    assert len(project(doc)['events'][0]['facts'][0]['numbers']) == 66


def test_empty_not_started_seed_does_not_claim_collection_or_ai():
    path = published_data._DATA_DIR / 'intelligence_investment_news.json'
    out = project(json.loads(path.read_text(encoding='utf-8')))
    assert out['status'] == 'NOT_STARTED' and out['events'] == [] and out['briefings'] == []
    assert not any(value is True for value in out['capabilities'].values())


def test_news_publication_validation_and_older_remote_retention(tmp_path):
    name = 'intelligence_investment_news.json'
    old = sample(); old['generated_at'] = '2026-10-21T00:59:00Z'
    new = sample(); new['events'][0]['summary'] = ['새 개정 요약']
    (tmp_path/name).write_text(json.dumps(old), encoding='utf-8')
    with patch.object(published_data, '_DATA_DIR', tmp_path), patch.object(published_data, '_CACHE', {}):
        with patch.object(published_data, 'urlopen', return_value=_Response(json.dumps(new).encode())):
            result, source = published_data.get_published_data(name)
        assert source == 'github-main' and result['events'][0]['summary'] == ['새 개정 요약']
        wrong_day = {**new, 'generated_at': '2026-10-21T15:00:00Z', 'as_of_date': '2026-10-21'}
        unsupported_return = copy.deepcopy(new)
        unsupported_return['events'][0]['performance'] = [{'return_pct': 20.0}]
        for candidate in (old, {**new, 'schemaVersion': 'invalid'}, wrong_day, unsupported_return):
            published_data._CACHE[name] = (0, result, source)
            with patch.object(published_data, 'urlopen', return_value=_Response(json.dumps(candidate).encode())):
                result, source = published_data.get_published_data(name)
            assert source == 'cached-published-fallback'
            assert result['events'][0]['summary'] == ['새 개정 요약']


def test_api_uses_existing_published_reader_no_store_and_preserves_analysis_dates():
    from intelligence_news_service import router
    app = FastAPI(); app.include_router(router)
    with patch('published_data.get_published_data', return_value=(sample(), 'github-main')) as read, TestClient(app) as client:
        response = client.get('/api/intelligence/news')
    read.assert_called_once_with('intelligence_investment_news.json')
    assert response.status_code == 200 and response.json() == sample()
    assert response.headers['cache-control'] == 'no-store, max-age=0, must-revalidate'
    assert response.headers['x-chartview-data-source'] == 'github-main'
    assert response.headers['x-chartview-data-asof'] == sample()['generated_at']


def test_api_failure_is_unavailable_without_private_error_detail():
    from intelligence_news_service import router
    app = FastAPI(); app.include_router(router)
    with patch('published_data.get_published_data', side_effect=ValueError('/private/path')), TestClient(app) as client:
        response = client.get('/api/intelligence/news')
    assert response.status_code == 503 and '/private' not in response.text


def test_no_existing_pick_payload_files_change():
    from pathlib import Path
    import subprocess
    changed = subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines()
    assert not {'static/data/ai_recommendations.json', 'static/data/ai_daily_rankings.json', 'static/data/pick_monitor.json'} & set(changed)
