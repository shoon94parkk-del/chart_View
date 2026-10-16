"""Calendar semantics and failure preservation for the separate inflation cache."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path

import pytest


def generator():
    return importlib.import_module('scripts.generate_inflation_release_cache')


def indices(start=2020, end=2026, base=100.0):
    return [{'month': f'{year}-{month:02d}', 'value': base + (year-start)*12 + month}
            for year in range(start, end+1) for month in range(1, 13)]


def test_changes_use_exact_calendar_month_and_separate_sa_nsa_baselines():
    mod = generator()
    sa = [{'month':'2025-01','value':100}, {'month':'2025-12','value':200},
          {'month':'2026-01','value':202}, {'month':'2026-03','value':303}]
    nsa = [{'month':'2025-01','value':80}, {'month':'2025-02','value':90},
           {'month':'2026-01','value':88}, {'month':'2026-03','value':99}]
    points = {p['month']:p for p in mod.build_points(sa, nsa)}
    assert points['2026-01']['mom'] == 1.0
    assert points['2026-01']['yoy'] == 10.0
    assert points['2026-03']['mom'] is None
    assert points['2026-03']['yoy'] is None


def test_csv_rejects_conflicting_duplicates_and_invalid_numbers():
    mod = generator()
    with pytest.raises(ValueError, match='duplicate'):
        mod.parse_fred_csv('observation_date,CPIAUCSL\n2026-01-01,100\n2026-01-01,101\n', 'CPIAUCSL')
    rows = mod.parse_fred_csv('observation_date,CPIAUCSL\n2026-01-01,100\n2026-02-01,.\n2026-03-01,NaN\n2026-04-01,0\n', 'CPIAUCSL')
    assert rows == [{'month':'2026-01','value':100.0}]


def test_points_keep_sixty_months_with_real_gaps_as_null():
    mod = generator()
    sa, nsa = indices(), indices(base=110)
    sa = [p for p in sa if p['month'] != '2025-12']
    points = mod.build_points(sa, nsa, months=60)
    assert len(points) == 60
    assert points[0]['month'] == '2022-01'
    assert next(p for p in points if p['month']=='2026-01')['mom'] is None
    assert next(p for p in points if p['month']=='2025-12')['mom'] is None
    assert points[-1]['yoy'] is not None


def test_series_metadata_keeps_observation_and_publication_separate():
    mod = generator()
    now = datetime(2026,10,16,tzinfo=timezone.utc)
    sa, nsa = indices(end=2025), indices(end=2025,base=120)
    row = mod.build_series('core_ppi', sa, nsa, now=now,
                           publication={'observationMonth':'2025-12','publishedAt':'2026-01-14T13:30:00Z','sourceUrl':'https://www.bls.gov/news.release/ppi.nr0.htm'})
    assert row['asOf'] == '2025-12'
    assert row['publishedAt'] == '2026-01-14T13:30:00Z'
    assert row['checkedAt'] == row['collectedAt'] == '2026-10-16T00:00:00Z'
    assert row['basis'] == {'yoy':'NSA','mom':'SA'}
    assert row['source']['saSeriesId'] == 'PPIFES'
    assert row['source']['nsaSeriesId'] == 'PPICOR'
    assert 'trade' not in row['definition'].lower()
    assert row['points'][0]['publishedAt'] is None
    assert row['revisionStatus'] == 'unknown'


def schedule_html(rows):
    return '<html><p>All times are Eastern Time.</p><table><tr><th>Reference Month</th><th>Release Date</th><th>Release Time</th></tr>'+''.join(
        '<tr>'+''.join('<td>'+cell+'</td>' for cell in row)+'</tr>' for row in rows)+'</table></html>'


def test_official_schedule_uses_reference_month_and_dst_without_invented_time():
    mod = generator()
    html = schedule_html([('October 2026','Nov. 10, 2026','08:30 AM'),
                          ('February 2027','Mar. 10, 2027','08:30 AM'),
                          ('March 2027','Apr. 13, 2027','08:30 AM'),
                          ('April 2027','May 12, 2027','')])
    events = mod.parse_schedule(html,'cpi',now=datetime(2026,10,16,tzinfo=timezone.utc))
    assert [(e['observationMonth'],e['scheduledAt']) for e in events] == [
        ('2026-10','2026-11-10T13:30:00Z'), ('2027-02','2027-03-10T13:30:00Z'),
        ('2027-03','2027-04-13T12:30:00Z'), ('2027-04',None)]
    assert events[-1]['localDate'] == '2027-05-12'
    assert events[-1]['localTime'] is None
    assert all(e['status']=='confirmed' and e['timeZone']=='America/New_York' for e in events)
    assert all(e['sourceUrl']=='https://www.bls.gov/schedule/news_release/cpi.htm' for e in events)


def test_publication_parser_requires_explicit_observation_month_and_exact_release_time():
    mod = generator()
    html = '<pre>Transmission of material in this release is embargoed until\n8:30 a.m. (ET) Wednesday, October 14, 2026\nCONSUMER PRICE INDEX - SEPTEMBER 2026</pre>'
    assert mod.parse_publication(html,'cpi') == {'observationMonth':'2026-09',
        'publishedAt':'2026-10-14T12:30:00Z', 'sourceUrl':'https://www.bls.gov/news.release/cpi.nr0.htm'}
    with pytest.raises(ValueError):
        mod.parse_publication('<h1>Consumer Price Index September 2026</h1>','cpi')


def test_failed_and_regressed_fetch_preserve_dated_values_and_successful_check_time():
    mod = generator()
    old_now = datetime(2026,10,15,tzinfo=timezone.utc)
    new_now = datetime(2026,10,16,tzinfo=timezone.utc)
    old = mod.build_series('cpi',indices(end=2025),indices(end=2025),now=old_now)
    previous = {'inflation':{'series':[old]},'releaseCalendar':{'status':'ok','checkedAt':'2026-10-15T00:00:00Z','events':[]}}
    pristine = deepcopy(previous)
    def unavailable(url):
        raise RuntimeError('source unavailable')
    failed = mod.refresh_cache(previous,now=new_now,fetch_text=unavailable)
    kept = next(r for r in failed['inflation']['series'] if r['id']=='cpi')
    for field in ('asOf','points','checkedAt','collectedAt'):
        assert kept[field] == old[field]
    assert kept['status']=='stale'
    assert failed['releaseCalendar']['checkedAt']=='2026-10-15T00:00:00Z'
    assert previous == pristine
    def regressed(url):
        if 'fredgraph.csv' in url:
            sid = url.split('id=')[1]
            return f'observation_date,{sid}\n2024-01-01,100\n2024-02-01,101\n'
        raise RuntimeError('source unavailable')
    regressed_result = mod.refresh_cache(previous,now=new_now,fetch_text=regressed)
    kept2 = next(r for r in regressed_result['inflation']['series'] if r['id']=='cpi')
    assert kept2['asOf']==old['asOf'] and kept2['checkedAt']==old['checkedAt']


def test_successful_unchanged_check_advances_check_without_claiming_publication_or_revision():
    mod = generator()
    now = datetime(2026,10,16,tzinfo=timezone.utc)
    old = mod.build_series('cpi',indices(end=2025),indices(end=2025),now=datetime(2026,10,15,tzinfo=timezone.utc))
    fresh = mod.build_series('cpi',indices(end=2025),indices(end=2025),now=now,previous=old)
    assert fresh['checkedAt']=='2026-10-16T00:00:00Z'
    assert fresh['asOf']==old['asOf'] and fresh['publishedAt'] is None
    assert fresh['revisionStatus']=='unknown'
    revised_sa = indices(end=2025)
    revised_sa[-2]['value'] += 0.5
    revised = mod.build_series('cpi',revised_sa,indices(end=2025),now=now,previous=old)
    assert revised['revisionStatus']=='revised'
    assert revised['revisionCheckedAt']=='2026-10-16T00:00:00Z'


def test_request_loader_is_file_only_and_omits_elapsed_events(tmp_path,monkeypatch):
    service = importlib.import_module('inflation_release_service')
    import requests
    monkeypatch.setattr(requests,'get',lambda *a,**k: pytest.fail('request-time provider call'))
    path = tmp_path/'cache.json'
    payload = {'inflation':{'schemaVersion':1,'status':'ok','series':[]},
               'releaseCalendar':{'status':'ok','events':[
                   {'id':'cpi:2026-09','scheduledAt':'2026-10-14T12:30:00Z'},
                   {'id':'cpi:2026-10','scheduledAt':'2026-11-10T13:30:00Z'},
                   {'id':'ppi:2026-10','scheduledAt':None,'localDate':'2026-11-13'}]}}
    path.write_text(json.dumps(payload))
    result = service.load_inflation_release_cache(path,now=datetime(2026,10,16,tzinfo=timezone.utc))
    assert [e['id'] for e in result['releaseCalendar']['events']]==['cpi:2026-10','ppi:2026-10']
    assert service.load_inflation_release_cache(tmp_path/'missing')['inflation']['status']=='unavailable'
    path.write_text('invalid json')
    assert service.load_inflation_release_cache(path)['releaseCalendar']['status']=='unavailable'


def test_malformed_schedule_cannot_break_other_successful_source_refreshes():
    mod = generator()
    now = datetime(2026,10,16,tzinfo=timezone.utc)
    def source(url):
        if 'fredgraph.csv' in url:
            sid = url.split('id=')[1]
            return 'observation_date,'+sid+'\n'+'\n'.join(p['month']+'-01,'+str(p['value']) for p in indices(end=2025))
        if '/schedule/' in url:
            return '<table></table>' if '/cpi.' in url else schedule_html([('October 2026','Nov. 13, 2026','08:30 AM')])
        raise RuntimeError('release metadata unavailable')
    result = mod.refresh_cache(now=now,fetch_text=source)
    assert all(row['status']=='ok' for row in result['inflation']['series'])
    assert result['releaseCalendar']['status']=='partial'
    assert [event['indicator'] for event in result['releaseCalendar']['events']]==['ppi']
    assert result['releaseCalendar']['sources']['cpi']['checkedAt'] is None


def test_date_only_agenda_uses_eastern_calendar_day(tmp_path):
    service = importlib.import_module('inflation_release_service')
    path = tmp_path/'cache.json'
    path.write_text(json.dumps({'inflation':{'series':[]},'releaseCalendar':{'events':[
        {'id':'cpi:2026-10','scheduledAt':None,'localDate':'2026-11-10'}]}}))
    # UTC has advanced to Nov11; the BLS local date is still Nov10.
    result = service.load_inflation_release_cache(path,now=datetime(2026,11,11,0,30,tzinfo=timezone.utc))
    assert len(result['releaseCalendar']['events'])==1


def test_partial_refresh_keeps_failed_pair_and_calendar_check_times_only():
    mod = generator()
    old_now = datetime(2026,10,15,tzinfo=timezone.utc)
    now = datetime(2026,10,16,tzinfo=timezone.utc)
    def source(url):
        if 'fredgraph.csv' in url:
            sid = url.split('id=')[1]
            return 'observation_date,'+sid+'\n'+'\n'.join(p['month']+'-01,'+str(p['value']) for p in indices(end=2025))
        if '/schedule/' in url:
            return schedule_html([('October 2026','Nov. 13, 2026','08:30 AM')])
        raise RuntimeError('publication metadata unavailable')
    previous = mod.refresh_cache(now=old_now,fetch_text=source)
    def partial(url):
        if 'id=CPIAUCSL' in url or '/schedule/news_release/cpi.htm' in url:
            raise RuntimeError('source temporarily unavailable')
        return source(url)
    result = mod.refresh_cache(previous,now=now,fetch_text=partial)
    rows = {row['id']:row for row in result['inflation']['series']}
    assert rows['cpi']['status']=='stale'
    assert rows['cpi']['checkedAt']=='2026-10-15T00:00:00Z'
    assert rows['core_cpi']['checkedAt']=='2026-10-16T00:00:00Z'
    calendar = result['releaseCalendar']
    assert calendar['status']=='partial'
    assert calendar['checkedAt']=='2026-10-15T00:00:00Z'
    assert calendar['sources']['cpi']['checkedAt']=='2026-10-15T00:00:00Z'
    assert calendar['sources']['ppi']['checkedAt']=='2026-10-16T00:00:00Z'
    assert next(e for e in calendar['events'] if e['indicator']=='cpi')['checkedAt']=='2026-10-15T00:00:00Z'


def test_reader_ignores_malformed_optional_event_without_breaking_legacy_macro(tmp_path):
    from inflation_release_service import load_inflation_release_cache
    path = tmp_path / 'inflation.json'
    path.write_text(json.dumps({'inflation': {'series': []}, 'releaseCalendar': {'events': [
        {'scheduledAt': 123}, {'scheduledAt': True}, {'scheduledAt': ['bad']},
        {'scheduledAt': '2026-11-10T13:30:00Z', 'id': 'valid'},
    ]}}))
    result = load_inflation_release_cache(path, now=datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert [row['id'] for row in result['releaseCalendar']['events']] == ['valid']


@pytest.fixture(autouse=True)
def prevent_unrequested_live_bls_calls(monkeypatch, request):
    if request.node.name == 'test_bls_transport_is_one_keyless_eight_series_post_with_25_second_timeout':
        return
    def unavailable(*args, **kwargs):
        raise RuntimeError('BLS test source unavailable')
    monkeypatch.setattr(generator(), 'fetch_bls_batch', unavailable, raising=False)


def bls_payload():
    """Independent official-ID fixture with real calendar missing/preliminary semantics."""
    ids = ['CUSR0000SA0','CUUR0000SA0','CUSR0000SA0L1E','CUUR0000SA0L1E',
           'WPSFD4','WPUFD4','WPSFD49104','WPUFD49104']
    series = []
    for offset, sid in enumerate(ids):
        data = []
        for point in indices(base=100+offset*10):
            if point['month'] > '2026-09':
                continue
            year, month = point['month'].split('-')
            missing = sid.startswith('CU') and point['month']=='2025-10'
            notes = ([{'code':'X','text':'Data unavailable due to the 2025 lapse in appropriations'}]
                     if missing else [{'code':'P','text':'Preliminary.'}] if sid.startswith('WP') and point['month']>='2026-06' else [{}])
            data.append({'year':year,'period':'M'+month,'value':'-' if missing else str(point['value']),'footnotes':notes})
        series.append({'seriesID':sid,'data':list(reversed(data))})
    return {'status':'REQUEST_SUCCEEDED','message':[],'Results':{'series':series}}


def unavailable_text(url):
    raise RuntimeError('primary unavailable')


def test_bls_parser_preserves_official_gaps_and_preliminary_footnotes():
    mod = generator()
    parsed = mod.parse_bls_batch(bls_payload())
    assert len(parsed['CUSR0000SA0'])==80
    assert not any(row['month']=='2025-10' for row in parsed['CUSR0000SA0'])
    assert parsed['WPSFD4'][-1]['footnotes']==[{'code':'P','text':'Preliminary.'}]
    payload = bls_payload()
    payload['status']='REQUEST_FAILED'
    with pytest.raises(ValueError,match='REQUEST_SUCCEEDED'):
        mod.parse_bls_batch(payload)
    payload = bls_payload()
    payload['Results']['series'][0]['data'].append({'year':'2026','period':'M09','value':'999','footnotes':[]})
    with pytest.raises(ValueError,match='duplicate'):
        mod.parse_bls_batch(payload)


def test_one_bls_fallback_recovers_all_failed_pairs_with_actual_provider_metadata():
    mod = generator();now=datetime(2026,10,16,tzinfo=timezone.utc);calls=[]
    def fallback(start,end):
        calls.append((start,end));return bls_payload()
    result = mod.refresh_cache(now=now,fetch_text=unavailable_text,fetch_bls=fallback)
    assert calls==[(2020,2026)]
    rows={row['id']:row for row in result['inflation']['series']}
    for key,row in rows.items():
        assert row['status'] in ('ok','partial')
        assert row['checkedAt']==row['collectedAt']=='2026-10-16T00:00:00Z'
        assert row['publishedAt'] is None
        assert row['source']['name']=='U.S. Bureau of Labor Statistics Public Data API'
        assert row['source']['url']=='https://api.bls.gov/publicAPI/v2/timeseries/data/'
        assert len(row['points'])==60
    assert rows['cpi']['source']['saSeriesId']=='CUSR0000SA0'
    assert rows['core_cpi']['source']['nsaSeriesId']=='CUUR0000SA0L1E'
    assert rows['ppi']['source']['saSeriesId']=='WPSFD4'
    assert rows['core_ppi']['source']['nsaSeriesId']=='WPUFD49104'
    assert rows['ppi']['observationStatus']=='preliminary'
    assert rows['ppi']['points'][-1]['sourceFootnotes']['mom']==[{'code':'P','text':'Preliminary.'}]
    gap=next(p for p in rows['cpi']['points'] if p['month']=='2025-10')
    assert gap['yoy'] is None and gap['mom'] is None


def test_successful_fred_pair_never_uses_bls_and_failed_pair_switches_atomically():
    mod=generator();calls=[];now=datetime(2026,10,16,tzinfo=timezone.utc)
    def primary(url):
        if 'fredgraph.csv' not in url:raise RuntimeError('metadata unavailable')
        sid=url.split('id=')[1]
        if sid=='CPIAUCSL':raise RuntimeError('one SA source failed')
        return 'observation_date,'+sid+'\n'+'\n'.join(p['month']+'-01,'+str(p['value']) for p in indices(end=2025))
    def fallback(start,end):
        calls.append((start,end));return bls_payload()
    result=mod.refresh_cache(now=now,fetch_text=primary,fetch_bls=fallback)
    rows={r['id']:r for r in result['inflation']['series']}
    assert calls==[(2020,2026)]
    assert rows['cpi']['source']['saSeriesId']=='CUSR0000SA0'
    assert rows['cpi']['source']['nsaSeriesId']=='CUUR0000SA0'
    assert rows['core_cpi']['source']['saSeriesId']=='CPILFESL'
    assert rows['ppi']['source']['saSeriesId']=='PPIFIS'
    def all_good(url):
        if 'id=CPIAUCSL' in url:
            return 'observation_date,CPIAUCSL\n'+'\n'.join(p['month']+'-01,'+str(p['value']) for p in indices(end=2025))
        return primary(url)
    calls.clear()
    mod.refresh_cache(now=now,fetch_text=all_good,fetch_bls=fallback)
    assert calls==[]


def test_partial_and_total_bls_failure_preserve_previous_successful_timestamps():
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc)
    first=mod.refresh_cache(now=datetime(2026,10,15,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:bls_payload())
    partial=bls_payload()
    partial['Results']['series']=[s for s in partial['Results']['series'] if s['seriesID']!='CUSR0000SA0']
    result=mod.refresh_cache(first,now=now,fetch_text=unavailable_text,fetch_bls=lambda *args:partial)
    rows={r['id']:r for r in result['inflation']['series']}
    assert rows['cpi']['status']=='stale' and rows['cpi']['checkedAt']=='2026-10-15T00:00:00Z'
    assert rows['core_cpi']['checkedAt']=='2026-10-16T00:00:00Z'
    total=mod.refresh_cache(first,now=now,fetch_text=unavailable_text,fetch_bls=lambda *args: {'status':'REQUEST_FAILED'})
    assert all(r['status']=='stale' and r['checkedAt']=='2026-10-15T00:00:00Z' for r in total['inflation']['series'])


def test_bls_fallback_keeps_only_observation_matching_old_publication():
    mod=generator();old=mod.build_series('cpi',indices(end=2025),indices(end=2025),now=datetime(2026,1,15,tzinfo=timezone.utc),publication={'observationMonth':'2025-12','publishedAt':'2026-01-14T13:30:00Z'})
    result=mod.refresh_cache({'inflation':{'series':[old]}},now=datetime(2026,10,16,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:bls_payload())
    row=result['inflation']['series'][0]
    assert row['asOf']=='2026-09' and row['publishedAt'] is None
    assert next(p for p in row['points'] if p['month']=='2025-12')['publishedAt']=='2026-01-14T13:30:00Z'


def ics_calendar(events):
    return 'BEGIN:VCALENDAR\nVERSION:2.0\n'+''.join('BEGIN:VEVENT\n'+event+'\nEND:VEVENT\n' for event in events)+'END:VCALENDAR\n'


def test_ics_uses_explicit_timezone_and_exact_old_match_without_inventing_reference_month():
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc)
    old=mod.parse_schedule(schedule_html([('October 2026','Nov. 10, 2026','08:30 AM')]),'cpi',now=datetime(2026,10,15,tzinfo=timezone.utc))
    text=ics_calendar(['UID:one\nSUMMARY:Consumer Price Index\nDTSTART;TZID=US-Eastern:20261110T083000',
                       'UID:two\nSUMMARY:Producer Price Index\nDTSTART;TZID=America/New_York:20270414T083000'])
    events=mod.parse_ics_calendar(text,now=now,previous_events=old)
    assert events[0]['scheduledAt']=='2026-11-10T13:30:00Z'
    assert events[0]['observationMonth']=='2026-10'
    assert events[1]['scheduledAt']=='2027-04-14T12:30:00Z'
    assert events[1]['observationMonth'] is None
    assert all(e['sourceUrl']=='https://www.bls.gov/schedule/news_release/bls.ics' for e in events)
    with pytest.raises(ValueError):
        mod.parse_ics_calendar(ics_calendar(['UID:bad\nSUMMARY:Consumer Price Index\nDTSTART:20261110T083000']),now=now)


def test_ics_refresh_checks_only_explicit_events_and_retains_uncovered_agenda():
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc);old_now=datetime(2026,10,15,tzinfo=timezone.utc)
    old_events=mod.parse_schedule(schedule_html([('October 2026','Nov. 10, 2026','08:30 AM'),('January 2027','Feb. 11, 2027','08:30 AM')]),'cpi',now=old_now)
    old_events+=mod.parse_schedule(schedule_html([('October 2026','Nov. 13, 2026','08:30 AM')]),'ppi',now=old_now)
    previous={'releaseCalendar':{'checkedAt':'2026-10-15T00:00:00Z','events':old_events,'sources':{g:{'checkedAt':'2026-10-15T00:00:00Z'} for g in ['cpi','ppi']}}}
    text=ics_calendar(['UID:cpi\nSUMMARY:Consumer Price Index\nDTSTART;TZID=US-Eastern:20261110T083000','UID:ppi\nSUMMARY:Producer Price Index\nDTSTART;TZID=US-Eastern:20261113T083000'])
    calls=[]
    def source(url):
        calls.append(url)
        if url.endswith('/bls.ics'):return text
        raise RuntimeError('HTML unavailable')
    result=mod.refresh_cache(previous,now=now,fetch_text=source)
    calendar=result['releaseCalendar']
    assert calls.count('https://www.bls.gov/schedule/news_release/bls.ics')==1
    assert len(calendar['events'])==3 and calendar['status']=='partial'
    assert calendar['checkedAt']=='2026-10-15T00:00:00Z'
    by_month={e['observationMonth']:e for e in calendar['events'] if e['indicator']=='cpi'}
    assert by_month['2026-10']['checkedAt']=='2026-10-16T00:00:00Z'
    assert by_month['2027-01']['checkedAt']=='2026-10-15T00:00:00Z'
    assert calendar['sources']['cpi']['status']=='partial'


def test_ics_explicit_utc_folded_lines_and_date_only_do_not_invent_time():
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc)
    text=ics_calendar(['UID:official-\n folded\nSUMMARY:Consumer Price Index\nDTSTART:20261110T133000Z',
                       'UID:date-only\nSUMMARY:Producer Price Index\nDTSTART;VALUE=DATE:20261113'])
    events=mod.parse_ics_calendar(text,now=now)
    assert events[0]['sourceUid']=='official-folded'
    assert events[0]['localTime']=='08:30' and events[0]['scheduledAt']=='2026-11-10T13:30:00Z'
    assert events[1]['localDate']=='2026-11-13' and events[1]['localTime'] is None and events[1]['scheduledAt'] is None
    assert events[0]['observationMonth'] is None
    with pytest.raises(ValueError):
        mod.parse_ics_calendar(ics_calendar(['UID:bad-zone\nSUMMARY:Consumer Price Index\nDTSTART;TZID=Unknown/Zone:20261110T083000']),now=now)


@pytest.mark.parametrize('local_time',['20270314T023000','20261101T013000'])
def test_ics_rejects_nonexistent_or_ambiguous_eastern_times(local_time):
    mod=generator()
    with pytest.raises(ValueError,match='ambiguous|nonexistent'):
        mod.parse_ics_calendar(ics_calendar(['UID:dst\nSUMMARY:Consumer Price Index\nDTSTART;TZID=America/New_York:'+local_time]),now=datetime(2026,10,16,tzinfo=timezone.utc))


def test_malformed_optional_bls_row_does_not_break_other_valid_pairs():
    mod=generator();payload=bls_payload()
    payload['Results']['series'][0]['data'].append(None)
    payload['Results']['series'].insert(0,None)
    result=mod.refresh_cache(now=datetime(2026,10,16,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:payload)
    assert all(row['status'] in ('ok','partial') for row in result['inflation']['series'])
    gap=result['inflation']['series'][0]['sourceGaps']['sa'][0]
    assert gap['month']=='2025-10' and gap['footnotes'][0]['code']=='X'


def test_one_malformed_bls_series_does_not_stale_other_valid_pairs():
    mod=generator();payload=bls_payload()
    previous=mod.refresh_cache(now=datetime(2026,10,15,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:bls_payload())
    payload['Results']['series'][0]['data']=None
    result=mod.refresh_cache(previous,now=datetime(2026,10,16,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:payload)
    rows={r['id']:r for r in result['inflation']['series']}
    assert rows['cpi']['status']=='stale' and rows['cpi']['checkedAt']=='2026-10-15T00:00:00Z'
    assert rows['core_cpi']['checkedAt']=='2026-10-16T00:00:00Z'


def test_ics_same_official_uid_replaces_old_time_and_keeps_verified_reference_month():
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc)
    old={'id':'cpi:2026-10','sourceUid':'official-cpi','indicator':'cpi','observationMonth':'2026-10',
         'scheduledAt':'2026-11-10T13:30:00Z','localDate':'2026-11-10','localTime':'08:30',
         'sourceUrl':'https://www.bls.gov/schedule/news_release/bls.ics','checkedAt':'2026-10-15T00:00:00Z'}
    text=ics_calendar(['UID:official-cpi\nSUMMARY:Consumer Price Index\nDTSTART;TZID=US-Eastern:20261111T083000'])
    def source(url):
        if url.endswith('/bls.ics'):return text
        raise RuntimeError('primary unavailable')
    result=mod.refresh_cache({'releaseCalendar':{'events':[old]}},now=now,fetch_text=source)
    rows=[e for e in result['releaseCalendar']['events'] if e['indicator']=='cpi']
    assert len(rows)==1 and rows[0]['scheduledAt']=='2026-11-11T13:30:00Z'
    assert rows[0]['observationMonth']=='2026-10'


def test_bls_transport_is_one_keyless_eight_series_post_with_25_second_timeout(monkeypatch):
    mod=generator();calls=[]
    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return bls_payload()
    def post(url,**kwargs):
        calls.append((url,kwargs));return Response()
    monkeypatch.setattr(mod.requests,'post',post)
    assert mod.fetch_bls_batch(2020,2026)['status']=='REQUEST_SUCCEEDED'
    assert len(calls)==1 and calls[0][0]=='https://api.bls.gov/publicAPI/v2/timeseries/data/'
    options=calls[0][1]
    assert options['timeout']==25
    assert options['json']=={'seriesid':['CUSR0000SA0','CUUR0000SA0','CUSR0000SA0L1E','CUUR0000SA0L1E','WPSFD4','WPUFD4','WPSFD49104','WPUFD49104'],'startyear':'2020','endyear':'2026'}
    calls.clear()
    def timeout(url,**kwargs):
        calls.append((url,kwargs));raise mod.requests.Timeout('source timeout')
    monkeypatch.setattr(mod.requests,'post',timeout)
    with pytest.raises(mod.requests.Timeout):
        mod.fetch_bls_batch(2020,2026)
    assert len(calls)==1


@pytest.mark.parametrize('with_time,with_other_event',[(True,True),(True,False),(False,False)])
def test_ics_cancellation_removes_old_uid_even_without_active_rows(with_time,with_other_event):
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc)
    old={'id':'cpi:2026-10','sourceUid':'official-cpi','indicator':'cpi','observationMonth':'2026-10',
         'scheduledAt':'2026-11-10T13:30:00Z','localDate':'2026-11-10','localTime':'08:30',
         'sourceUrl':mod.ICS_URL,'checkedAt':'2026-10-15T00:00:00Z'}
    cancelled='UID:official-cpi\nSUMMARY:Consumer Price Index\nSTATUS:CANCELLED'
    if with_time:cancelled+='\nDTSTART;TZID=US-Eastern:20261110T083000'
    records=[cancelled]
    if with_other_event:records.append('UID:ppi\nSUMMARY:Producer Price Index\nDTSTART;TZID=US-Eastern:20261113T083000')
    def source(url):
        if url==mod.ICS_URL:return ics_calendar(records)
        raise RuntimeError('HTML unavailable')
    result=mod.refresh_cache({'releaseCalendar':{'events':[old]}},now=now,fetch_text=source)
    assert not any(e['id']=='cpi:2026-10' for e in result['releaseCalendar']['events'])
    assert result['releaseCalendar']['sources']['cpi']['cancelledEventCount']==1
    assert result['releaseCalendar']['sources']['cpi']['checkedAt']=='2026-10-16T00:00:00Z'


def test_ics_replacement_quarantines_uidless_html_seed_in_covered_release_month():
    mod=generator();now=datetime(2026,10,16,tzinfo=timezone.utc)
    old=mod.parse_schedule(schedule_html([('October 2026','Nov. 10, 2026','08:30 AM'),('January 2027','Feb. 11, 2027','08:30 AM')]),'cpi',now=datetime(2026,10,15,tzinfo=timezone.utc))
    def source(url):
        if url==mod.ICS_URL:return ics_calendar(['UID:replacement\nSUMMARY:Consumer Price Index\nDTSTART;TZID=US-Eastern:20261111T083000'])
        raise RuntimeError('HTML unavailable')
    result=mod.refresh_cache({'releaseCalendar':{'checkedAt':'2026-10-15T00:00:00Z','events':old}},now=now,fetch_text=source)
    events=result['releaseCalendar']['events']
    assert not any(e['scheduledAt']=='2026-11-10T13:30:00Z' for e in events)
    replacement=next(e for e in events if e.get('sourceUid')=='replacement')
    assert replacement['observationMonth'] is None
    far=next(e for e in events if e['scheduledAt']=='2027-02-11T13:30:00Z')
    assert far['checkedAt']=='2026-10-15T00:00:00Z'
    assert result['releaseCalendar']['status']=='partial'


@pytest.mark.parametrize('second_status',['','STATUS:CANCELLED\n'])
def test_ics_rejects_duplicate_uid_across_active_or_cancelled_events(second_status):
    mod=generator();text=ics_calendar(['UID:duplicate\nSUMMARY:Consumer Price Index\nDTSTART;TZID=US-Eastern:20261110T083000',
        'UID:duplicate\nSUMMARY:Consumer Price Index\n'+second_status+'DTSTART;TZID=US-Eastern:20261111T083000'])
    with pytest.raises(ValueError,match='duplicate.*UID'):
        mod.parse_ics_calendar(text,now=datetime(2026,10,16,tzinfo=timezone.utc))


def test_bls_boolean_value_is_not_a_numeric_observation():
    mod=generator();payload=bls_payload()
    payload['Results']['series'][0]['data'][0]['value']=True
    parsed=mod.parse_bls_batch(payload)
    assert not any(p['month']=='2026-09' for p in parsed['CUSR0000SA0'])


def test_definition_carries_only_verified_latest_preliminary_note():
    mod=generator();result=mod.refresh_cache(now=datetime(2026,10,16,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:bls_payload())
    rows={r['id']:r for r in result['inflation']['series']}
    note=' 최근 값은 잠정치로 추후 수정될 수 있어요.'
    assert rows['core_ppi']['definition']==mod.SERIES['core_ppi']['definition']+note
    assert rows['cpi']['definition']==mod.SERIES['cpi']['definition']
    payload=bls_payload()
    for series in payload['Results']['series']:
        series['data'][0]['footnotes']=[]
    result2=mod.refresh_cache(now=datetime(2026,10,16,tzinfo=timezone.utc),fetch_text=unavailable_text,fetch_bls=lambda *args:payload)
    assert all(r['definition']==mod.SERIES[r['id']]['definition'] for r in result2['inflation']['series'])
