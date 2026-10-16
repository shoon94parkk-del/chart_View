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
