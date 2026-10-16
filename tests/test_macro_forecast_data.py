"""Optional licensed forecast receipts; synthetic values below are test fixtures only."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json

import pytest

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
RETRIEVED = '2026-10-16T00:00:00Z'


def forecast(**overrides):
    value = {'seriesId': 'cpi', 'month': '2026-09', 'rate': 'yoy', 'basis': 'NSA', 'unit': '%',
             'expected': 0, 'evidenceKind': 'provider_archive', 'retrievedAt': RETRIEVED,
             'archive': {'url': 'https://vendor.example/archive/one', 'eventId': 'event-one', 'contentSha256': 'a'*64},
             'source': {'forecastName': 'Licensed survey', 'forecastUrl': 'https://vendor.example/archive/one'}}
    value.update(overrides)
    return value


def comparison(**overrides):
    value = forecast(actual=0, actualVintage='first_release', publishedAt='2026-10-14T12:30:00Z')
    value['source'].update(actualName='BLS', actualUrl='https://www.bls.gov/news.release/cpi.nr0.htm')
    value.update(overrides)
    return value


def load(tmp_path, forecasts=None, comparisons=None, *, status='ok', legacy=None, mutate=None):
    from inflation_release_service import load_inflation_release_cache
    row = {'id': 'cpi', 'asOf': '2026-09', 'basis': {'yoy': 'NSA', 'mom': 'SA'}, 'unit': '%',
           'points': [{'month': '2026-09', 'yoy': 4.2, 'mom': 0.1, 'publishedAt': '2026-10-14T12:30:00Z'}]}
    if legacy is not None:
        row['comparisons'] = legacy
    payload = {'inflation': {'schemaVersion': 1, 'status': 'ok', 'series': [row]},
               'releaseCalendar': {'status': 'ok', 'events': []}}
    cache = {'schemaVersion': 1, 'provider': 'Trading Economics', 'status': status, 'checkedAt': RETRIEVED,
             'forecasts': forecasts or [], 'comparisons': comparisons or []}
    if mutate:
        mutate(cache)
    base, path = tmp_path/'inflation.json', tmp_path/'forecasts.json'
    base.write_text(json.dumps(payload))
    path.write_text(json.dumps(cache))
    result = load_inflation_release_cache(base, forecast_path=path, now=NOW)
    assert result['inflation']['series'][0]['points'] == row['points']
    return result['inflation']['series'][0]


def module():
    # Fail as an assertion until the documented optional adapter exists.
    from pathlib import Path
    assert Path('scripts/macro_forecast_data.py').is_file(), 'optional offline adapter is missing'
    return importlib.import_module('scripts.macro_forecast_data')


def test_reader_post_release_archive_displays_forecast_zero_without_first_release_claim(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests, 'get', lambda *a, **k: pytest.fail('request provider IO'))
    monkeypatch.setattr(requests, 'post', lambda *a, **k: pytest.fail('request provider IO'))
    row = load(tmp_path, [forecast()])
    assert row['forecasts'][0]['expected'] == 0
    assert row.get('comparisons', []) == []
    assert row['forecastCoverage'] == {'status': 'ok', 'provider': 'Trading Economics', 'checkedAt': RETRIEVED,
                                       'forecastCount': 1, 'comparisonCount': 0}


@pytest.mark.parametrize('change', [
    {'month':'2026-08'}, {'basis':'SA'}, {'seriesId':'not_cpi'}, {'rate':'qoq'}, {'unit':'index'},
    {'expected':True}, {'expected':float('nan')}, {'expected':'0'}, {'retrievedAt':'2026-10-17T00:00:00Z'},
    {'retrievedAt':'2026-10-16'}, {'evidenceKind':'scraped'},
    {'archive':{'url':'http://vendor.example/x','eventId':'one','contentSha256':'a'*64}},
    {'archive':{'url':'https://user:secret@vendor.example/x','eventId':'one','contentSha256':'a'*64}},
    {'archive':{'url':'https://vendor.example/x?c=secret','eventId':'one','contentSha256':'a'*64}},
    {'archive':{'url':'https://127.0.0.1/x','eventId':'one','contentSha256':'a'*64}},
    {'archive':{'url':'https://vendor.example/x','eventId':'','contentSha256':'a'*64}},
    {'archive':{'url':'https://vendor.example/x','eventId':'one','contentSha256':'nohash'}},
    {'source':{'forecastName':'survey','forecastUrl':'javascript:alert(1)'}},
])
def test_reader_rejects_wrong_period_basis_or_unsafe_incomplete_archive(tmp_path, change):
    assert load(tmp_path, [forecast(**change)]).get('forecasts', []) == []


def test_reader_quarantines_duplicates_instead_of_picking_a_convenient_value(tmp_path):
    row = load(tmp_path, [forecast(), forecast(expected=9)])
    assert row.get('forecasts', []) == []
    assert row['forecastCoverage']['status'] == 'partial'


def test_reader_preserves_legacy_receipts_and_requires_evidenced_official_first_release(tmp_path):
    legacy = [{'month':'2025-12','legacy':'unchanged'}]
    receipt = comparison()
    row = load(tmp_path, [forecast()], [receipt], legacy=legacy)
    assert row['comparisons'] == legacy + [receipt]
    assert row['comparisons'][-1]['actual'] == 0
    assert row['forecastCoverage']['comparisonCount'] == 1


@pytest.mark.parametrize('change', [
    {'actualVintage':'current'}, {'actual':True}, {'publishedAt':'2026-10-15T12:30:00Z'},
    {'publishedAt':'2026-10-17T12:30:00Z'}, {'source':{'forecastName':'Survey','forecastUrl':'https://vendor.example/x'}}
])
def test_reader_rejects_unverified_archive_comparison_but_keeps_forecast(tmp_path, change):
    row = load(tmp_path, [forecast()], [comparison(**change)])
    assert len(row['forecasts']) == 1
    assert row.get('comparisons', []) == []


def test_reader_legacy_capture_guard_stays_strict(tmp_path):
    receipt = comparison(evidenceKind='captured_before', forecastPublishedAt='2026-10-13T12:00:00Z',
                         forecastCapturedAt='2026-10-13T13:00:00Z')
    assert len(load(tmp_path, comparisons=[receipt]).get('comparisons', [])) == 1
    receipt['forecastCapturedAt'] = receipt['publishedAt']
    assert load(tmp_path, comparisons=[receipt]).get('comparisons', []) == []
    receipt.pop('evidenceKind')
    assert load(tmp_path, comparisons=[receipt]).get('comparisons', []) == []


def test_missing_or_unconfigured_forecast_cache_is_explicit_and_preserves_legacy(tmp_path):
    row = load(tmp_path, [forecast()], status='not_configured', legacy=[{'old':True}])
    assert row.get('forecasts', []) == []
    assert row['comparisons'] == [{'old':True}]
    assert row['forecastCoverage']['status'] == 'not_configured'
    from inflation_release_service import load_inflation_release_cache
    result = load_inflation_release_cache(tmp_path/'inflation.json', forecast_path=tmp_path/'missing', now=NOW)
    assert result['inflation']['series'][0]['forecastCoverage']['status'] == 'not_configured'


def te_raw(**changes):
    row = {'CalendarId':'explicit-event', 'ReferenceDate':'2026-09-01T00:00:00', 'Date':'2026-10-14T12:30:00',
           'Forecast':'0%', 'Unit':'%', 'Actual':'99%', 'TEForecast':'8%', 'LastUpdate':'2026-10-10T01:00:00'}
    row.update(changes)
    return json.dumps([row]).encode()


def adapt(raw=None, **changes):
    options = dict(event_mapping={'explicit-event':{'seriesId':'cpi','rate':'yoy','basis':'NSA'}},
                   archive_url='https://vendor.example/archive/one', retrieved_at=RETRIEVED, rights_confirmed=True, now=NOW)
    options.update(changes)
    return module().build_te_cache(raw or te_raw(), **options)


def test_te_adapter_only_uses_explicit_mapping_reference_month_and_survey_forecast():
    cache = adapt()
    row = cache['forecasts'][0]
    assert row['month'] == '2026-09' and row['expected'] == 0
    assert row['evidenceKind'] == 'provider_archive'
    assert row['archive']['eventId'] == 'explicit-event'
    import hashlib
    assert row['archive']['contentSha256'] == hashlib.sha256(te_raw()).hexdigest()
    assert 'forecastPublishedAt' not in row and 'forecastCapturedAt' not in row
    assert cache['comparisons'] == []  # TE Actual is latest, not first release.
    assert adapt(te_raw(CalendarID='explicit-event', CalendarId=None, ForecastValue=0))['forecasts'][0]['expected'] == 0


@pytest.mark.parametrize('raw,options', [
    (te_raw(ReferenceDate=None), {}), (te_raw(ReferenceDate='Sep'), {}),
    (te_raw(Forecast=None), {}), (te_raw(Forecast='--'), {}),
    (te_raw(Unit='index'), {}), (te_raw(CalendarId='unknown'), {}),
    (te_raw(), {'event_mapping':{'explicit-event':{'seriesId':'cpi','rate':'yoy','basis':'SA'}}}),
])
def test_te_adapter_never_guesses_event_period_unit_or_model_forecast(raw, options):
    assert adapt(raw, **options)['forecasts'] == []


def test_te_adapter_rights_default_disables_transport_and_cache_values():
    mod = module()
    assert adapt(rights_confirmed=False)['status'] == 'not_configured'
    cache = mod.fetch_te_cache(lambda: pytest.fail('disabled provider IO'), rights_confirmed=False)
    assert cache['status'] == 'not_configured' and cache['forecasts'] == []


def test_offline_adapter_enforces_raw_byte_and_row_bounds():
    mod = module()
    with pytest.raises(ValueError, match='byte'):
        adapt(max_bytes=8)
    with pytest.raises(ValueError, match='row'):
        adapt(json.dumps([json.loads(te_raw())[0]]*3).encode(), max_rows=2)
    with pytest.raises(ValueError, match='duplicate'):
        adapt(json.dumps([json.loads(te_raw())[0]]*2).encode())
    cache = mod.fetch_te_cache(lambda: te_raw(), rights_confirmed=True,
        event_mapping={'explicit-event':{'seriesId':'cpi','rate':'yoy','basis':'NSA'}},
        archive_url='https://vendor.example/archive/one', retrieved_at=RETRIEVED, now=NOW)
    assert cache['forecasts'][0]['expected'] == 0


def test_cache_rejects_unsupported_schema_malformed_and_oversize_documents(tmp_path):
    mod = module()
    path = tmp_path/'cache.json'
    path.write_text('{')
    assert mod.load_cache(path)['status'] == 'unavailable'
    path.write_bytes(b' '* (mod.MAX_BYTES + 1))
    assert mod.load_cache(path)['status'] == 'unavailable'
    row = load(tmp_path, [forecast()], mutate=lambda value: value.update(schemaVersion=2))
    assert row['forecastCoverage']['status'] == 'unavailable'
    assert row['forecasts'] == []


def test_default_capture_kind_requires_real_prerelease_receipt(tmp_path):
    receipt = comparison(forecastPublishedAt='2026-10-13T12:00:00Z', forecastCapturedAt='2026-10-13T13:00:00Z')
    receipt.pop('evidenceKind')
    assert load(tmp_path, comparisons=[receipt])['comparisons'] == [receipt]
    receipt['forecastPublishedAt'] = '2026-10-13T14:00:00Z'
    assert load(tmp_path, comparisons=[receipt]).get('comparisons', []) == []


def test_cached_comparison_duplicates_do_not_override_existing_legacy(tmp_path):
    legacy = comparison()
    legacy.pop('seriesId')
    row = load(tmp_path, comparisons=[comparison(), comparison(actual=1)], legacy=[legacy])
    assert row['comparisons'] == [legacy]


def test_actual_receipt_requires_official_source_and_matches_official_eastern_date(tmp_path):
    source = deepcopy(comparison()['source'])
    source['actualUrl'] = 'https://vendor.example/actual'
    assert load(tmp_path, comparisons=[comparison(source=source)]).get('comparisons', []) == []
    mod = module()
    series = {'asOf':'2026-09','publishedAt':None,'publishedDate':'2026-10-14','points':[]}
    receipt = comparison(publishedAt='2026-10-15T02:00:00Z')
    assert mod.comparison_valid(receipt, series, NOW)  # Still Oct 14 in New York.
    receipt['publishedAt'] = '2026-10-15T12:30:00Z'
    assert not mod.comparison_valid(receipt, series, NOW)


def test_te_core_pce_mapping_uses_sa_for_yoy_and_keeps_missing_consensus_missing():
    mapped = {'explicit-event':{'seriesId':'core_pce','rate':'yoy','basis':'SA'}}
    receipt = adapt(event_mapping=mapped)['forecasts'][0]
    assert receipt['basis'] == 'SA' and receipt['seriesId'] == 'core_pce'
    assert adapt(te_raw(Forecast=None, TEForecastValue=9), event_mapping=mapped)['forecasts'] == []


def test_offline_cli_without_rights_writes_no_values_and_never_reads_input(tmp_path, monkeypatch):
    import sys
    mod = module()
    output = tmp_path/'output.json'
    monkeypatch.setattr(sys, 'argv', ['macro_forecast_data.py', '--input', str(tmp_path/'absent'),
        '--mapping', str(tmp_path/'also-absent'), '--archive-url', 'https://vendor.example/archive',
        '--retrieved-at', RETRIEVED, '--output', str(output)])
    mod.main()
    assert json.loads(output.read_text()) == mod.empty_cache()


def test_reader_bad_optional_receipt_never_breaks_sibling_rows_or_leaks_partial_status(tmp_path):
    mod = module()
    inflation = {'series':[
        {'id':'cpi','asOf':'2026-09','basis':{'yoy':'NSA'},'unit':'%','points':[]},
        {'id':'core_pce','asOf':'2026-09','basis':{'yoy':'SA'},'unit':'%','points':[]}]}
    cache = {'provider':'Trading Economics','status':'ok','checkedAt':RETRIEVED,'forecasts':[
        forecast(basis='SA'), forecast(seriesId='core_pce',basis='SA')], 'comparisons':[]}
    mod.attach_forecasts(inflation, cache, now=NOW)
    assert inflation['series'][0]['forecastCoverage']['status'] == 'partial'
    assert inflation['series'][1]['forecastCoverage']['status'] == 'ok'
    assert inflation['forecastCoverage']['status'] == 'partial'


@pytest.mark.parametrize('change', [{'expected':10**1000}, {'rate':[]}, {'basis':{}}, {'seriesId':[]}])
def test_malformed_receipt_types_are_ignored_without_reader_failure(tmp_path, change):
    assert load(tmp_path, [forecast(**change)])['forecasts'] == []


def test_te_conflicting_event_id_aliases_cannot_select_a_convenient_mapping():
    assert adapt(te_raw(CalendarID='explicit-event', CalendarId='different-event'))['forecasts'] == []


def test_nested_optional_json_failure_preserves_all_saved_numeric_histories(tmp_path):
    from inflation_release_service import load_inflation_release_cache
    baseline = load(tmp_path, legacy=[{'old':'preserved'}])
    path = tmp_path/'forecasts.json'
    path.write_text('[' * 10000 + '0' + ']' * 10000)
    result = load_inflation_release_cache(tmp_path/'inflation.json', forecast_path=path, now=NOW)
    row = result['inflation']['series'][0]
    assert row['points'] == baseline['points']
    assert row['comparisons'] == baseline['comparisons']
    assert row['forecastCoverage']['status'] == 'unavailable'
    assert row['forecasts'] == []


@pytest.mark.parametrize('query', ['api-key=redacted-test', 'client_secret=redacted-test', 'accessToken=redacted-test', 'period=2026-09'])
def test_reader_and_importer_reject_all_query_bearing_public_evidence(tmp_path, query):
    url = 'https://vendor.example/archive?' + query
    receipt = forecast()
    receipt['archive']['url'] = url
    receipt['source']['forecastUrl'] = url
    assert load(tmp_path, [receipt])['forecasts'] == []
    with pytest.raises(ValueError, match='archive'):
        adapt(archive_url=url)


def test_historical_forecast_survives_without_unverified_first_release_comparison():
    mod = module()
    series = {'id':'cpi','asOf':'2026-09','basis':{'yoy':'NSA','mom':'SA'},'unit':'%',
              'points':[{'month':'2021-10','yoy':6.2,'mom':0.9,'publishedAt':None}]}
    saved = deepcopy(series['points'])
    future_release = comparison(month='2021-10', publishedAt='2021-11-10T13:30:00Z')
    future_release['source']['actualUrl'] = 'https://www.bls.gov/news.release/archives/cpi_11102021.htm'
    cache = {'provider':'Trading Economics','status':'ok','checkedAt':RETRIEVED,
             'forecasts':[forecast(month='2021-10')], 'comparisons':[future_release]}
    mod.attach_forecasts({'series':[series]}, cache, now=NOW)
    assert series['points'] == saved
    assert len(series['forecasts']) == 1
    assert series.get('comparisons', []) == []
    assert series['forecastCoverage']['status'] == 'partial'


def test_first_release_cannot_precede_or_fall_within_observation_month_even_if_saved_metadata_is_bad():
    mod = module()
    for release in ('2020-01-01T12:30:00Z', '2021-10-31T23:59:00Z'):
        series = {'asOf':'2021-10','points':[{'month':'2021-10','publishedAt':release}]}
        assert not mod.comparison_valid(comparison(month='2021-10', publishedAt=release), series, NOW)


def test_generic_official_homepage_is_not_original_release_evidence(tmp_path):
    receipt = comparison()
    receipt['source']['actualUrl'] = 'https://www.bls.gov/'
    assert load(tmp_path, comparisons=[receipt]).get('comparisons', []) == []


@pytest.mark.parametrize('change', [
    {'expected':9}, {'retrievedAt':'2026-10-15T00:00:00Z'},
    {'archive':{'url':'https://vendor.example/archive/two','eventId':'event-one','contentSha256':'a'*64}},
    {'archive':{'url':'https://vendor.example/archive/one','eventId':'event-two','contentSha256':'a'*64}},
    {'archive':{'url':'https://vendor.example/archive/one','eventId':'event-one','contentSha256':'b'*64}},
    {'source':{'forecastName':'Different survey','forecastUrl':'https://vendor.example/archive/one',
               'actualUrl':'https://www.bls.gov/news.release/cpi.nr0.htm'}}
])
def test_cross_collection_conflicting_expectation_or_provenance_quarantines_both(tmp_path, change):
    row = load(tmp_path, [forecast()], [comparison(**change)], legacy=[{'old':'preserved'}])
    assert row['forecasts'] == []
    assert row['comparisons'] == [{'old':'preserved'}]
    assert row['forecastCoverage']['status'] == 'partial'


def test_strict_json_duplicate_fields_are_unavailable_and_import_fails_before_replacement(tmp_path, monkeypatch):
    import sys
    mod = module()
    path = tmp_path/'ambiguous.json'
    path.write_text('{"schemaVersion":1,"schemaVersion":2}')
    assert mod.load_cache(path)['status'] == 'unavailable'
    provider = tmp_path/'provider.json'
    provider.write_bytes(te_raw().replace(b'"Forecast": "0%"', b'"Forecast": "9%", "Forecast": "0%"'))
    mapping = tmp_path/'mapping.json'
    mapping.write_text(json.dumps({'explicit-event':{'seriesId':'cpi','rate':'yoy','basis':'NSA'}}))
    output = tmp_path/'existing.json'
    output.write_text('keep existing cache')
    monkeypatch.setattr(sys, 'argv', ['macro_forecast_data.py','--input',str(provider),'--mapping',str(mapping),
        '--output',str(output),'--archive-url','https://vendor.example/archive', '--retrieved-at',RETRIEVED,'--rights-confirmed'])
    with pytest.raises(ValueError, match='duplicate'):
        mod.main()
    assert output.read_text() == 'keep existing cache'


@pytest.mark.parametrize('release', ['0001-01-01T00:00:00Z', '0001-01-01T00:00:00+23:59'])
def test_out_of_range_release_timezone_preserves_saved_rates_and_valid_forecast(tmp_path, release):
    row = load(tmp_path, [forecast()], [comparison(publishedAt=release)], legacy=[{'old':'preserved'}])
    assert row['points'] == [{'month':'2026-09','yoy':4.2,'mom':0.1,'publishedAt':'2026-10-14T12:30:00Z'}]
    assert row['forecasts'] == [forecast()]
    assert row['comparisons'] == [{'old':'preserved'}]
    assert row['forecastCoverage']['status'] == 'partial'
