"""PCE extends the optional cache without changing the four BLS indicators."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from test_inflation_release_cache import generator, indices, schedule_html
from test_pce_release_data import workbook

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
NEWS_URL = 'https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026'
NEWS = '<h1>Personal Income and Outlays, August 2026</h1><p>EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Wednesday, September 30, 2026</p>'


def source(*, bad=None, news=NEWS, blob=None):
    mod = generator()
    calls = []
    def fetch(url):
        calls.append(url)
        from scripts import pce_release_data as pce
        if url == pce.WORKBOOK_URL:
            if bad == 'workbook':
                raise RuntimeError('BEA unavailable')
            return blob or workbook()
        if url == pce.PRODUCT_URL:
            return '<a href="' + NEWS_URL + '">Current Release</a>'
        if url == NEWS_URL:
            if bad == 'news':
                raise RuntimeError('BEA release unavailable')
            return news
        if url == pce.RELEASE_DATES_URL:
            if bad == 'calendar':
                raise RuntimeError('BEA calendar unavailable')
            return json.dumps({'Personal Income and Outlays': {'release_dates': ['2026-10-29T12:30:00+00:00', '2026-11-25T13:30:00+00:00']}})
        if 'fredgraph.csv' in url:
            sid = url.split('id=')[1]
            return 'observation_date,' + sid + '\n' + '\n'.join(p['month'] + '-01,' + str(p['value']) for p in indices(end=2025))
        if url in mod.SCHEDULE_URLS.values():
            return schedule_html([('October 2026', 'Nov. 13, 2026', '08:30 AM')])
        raise RuntimeError('publication metadata not supplied')
    return fetch, calls


def rows(result):
    return {row['id']: row for row in result['inflation']['series']}


def test_pce_uses_one_shared_bea_workbook_and_same_sa_for_both_changes():
    mod = generator()
    fetch, calls = source()
    result = mod.refresh_cache(now=NOW, fetch_text=fetch)
    current = rows(result)
    assert set(current) == {'cpi', 'core_cpi', 'ppi', 'core_ppi', 'pce', 'core_pce'}
    pce = current['pce']
    assert pce['basis'] == {'yoy': 'SA', 'mom': 'SA'}
    assert set(pce['sourceIndices']) == {'sa'}
    assert len(pce['sourceIndices']['sa']) == 72 and len(pce['points']) == 60
    assert pce['points'][-1]['yoy'] == round((107.1 / 105.9 - 1) * 100, 6)
    assert pce['points'][-1]['mom'] == round((107.1 / 107.0 - 1) * 100, 6)
    assert pce['asOf'] == '2026-08' and pce['publishedAt'] == '2026-09-30T12:30:00Z'
    assert pce['publicationPrecision'] == 'second'
    assert pce['publicationSourceUrl'] == NEWS_URL
    assert pce['source']['beaAccountCode'] == 'DPCERG'
    assert current['core_pce']['source']['beaAccountCode'] == 'DPCCRG'
    assert all(current[sid]['basis'] == {'yoy': 'NSA', 'mom': 'SA'} for sid in mod.SERIES)
    from scripts import pce_release_data as helper
    assert Counter(calls)[helper.WORKBOOK_URL] == 1
    assert Counter(calls)[NEWS_URL] == 1
    assert result['inflation']['status'] == 'ok'


def test_date_only_workbook_fallback_never_invents_release_time():
    fetch, _ = source(bad='news')
    pce = rows(generator().refresh_cache(now=NOW, fetch_text=fetch))['pce']
    assert pce['publishedDate'] == '2026-09-30'
    assert pce['publishedAt'] == '2026-09-30'
    assert pce['publicationPrecision'] == 'day'
    assert all(p['publishedAt'] is None for p in pce['points'])


@pytest.mark.parametrize('failure', ['workbook', 'newer_publication', 'future_publication', 'future_observation', 'regression'])
def test_invalid_pce_refresh_preserves_previous_verified_data_and_times(failure):
    mod = generator()
    old_fetch, _ = source()
    previous = mod.refresh_cache(now=datetime(2026, 10, 15, tzinfo=timezone.utc), fetch_text=old_fetch)
    if failure == 'regression':
        for row in previous['inflation']['series']:
            if row['id'] in ('pce', 'core_pce'):
                row['asOf'] = '2026-09'
    pristine = deepcopy(previous)
    if failure == 'newer_publication':
        fetch, _ = source(news=NEWS.replace('August 2026', 'September 2026').replace('September 30, 2026', 'October 1, 2026'))
    elif failure == 'future_publication':
        fetch, _ = source(news=NEWS.replace('September 30, 2026', 'October 30, 2026'))
    elif failure == 'future_observation':
        fetch, _ = source(blob=workbook(months=74))
    else:
        fetch, _ = source(bad='workbook' if failure == 'workbook' else None)
    result = mod.refresh_cache(previous, now=NOW, fetch_text=fetch)
    for sid in ('pce', 'core_pce'):
        old, kept = rows(previous)[sid], rows(result)[sid]
        assert kept['status'] == 'stale'
        for field in ('asOf', 'points', 'sourceIndices', 'checkedAt', 'collectedAt', 'publishedAt'):
            assert kept[field] == old[field], field
    assert previous == pristine


def test_confirmed_bea_calendar_does_not_guess_reference_month_and_preserves_dst():
    fetch, _ = source()
    result = generator().refresh_cache(now=NOW, fetch_text=fetch)
    events = [e for e in result['releaseCalendar']['events'] if e['indicator'] == 'pce']
    assert len(events) == 2
    assert [(e['scheduledAt'], e['localTime']) for e in events] == [('2026-10-29T12:30:00Z', '08:30'), ('2026-11-25T13:30:00Z', '08:30')]
    assert all(e['observationMonth'] is None and e['timeZone'] == 'America/New_York' and e['status'] == 'confirmed' for e in events)
    assert result['releaseCalendar']['sources']['pce']['status'] == 'ok'


def test_bea_calendar_failure_retains_its_previous_check_and_events():
    mod = generator()
    fetch, _ = source()
    previous = mod.refresh_cache(now=datetime(2026, 10, 15, tzinfo=timezone.utc), fetch_text=fetch)
    fetch, _ = source(bad='calendar')
    result = mod.refresh_cache(previous, now=NOW, fetch_text=fetch)
    assert result['releaseCalendar']['sources']['pce']['checkedAt'] == '2026-10-15T00:00:00Z'
    retained = [e for e in result['releaseCalendar']['events'] if e['indicator'] == 'pce']
    assert retained and all(e['checkStatus'] == 'stale' and e['checkedAt'] == '2026-10-15T00:00:00Z' for e in retained)


def test_first_bea_calendar_failure_is_partial_without_claiming_full_freshness():
    fetch, _ = source(bad='calendar')
    result = generator().refresh_cache(now=NOW, fetch_text=fetch)
    calendar = result['releaseCalendar']
    assert calendar['status'] == 'partial'
    assert calendar['checkedAt'] is None
    assert calendar['sources']['pce']['status'] == 'unavailable'
    assert calendar['sources']['pce']['checkedAt'] is None
    assert all(calendar['sources'][group]['checkedAt'] == '2026-10-16T00:00:00Z' for group in ('cpi', 'ppi'))
    assert all(row['status'] == 'ok' for row in result['inflation']['series'])
