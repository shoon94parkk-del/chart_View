"""An official newer reference month must invalidate an older successful feed."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from test_inflation_release_cache import bls_payload, generator, indices, schedule_html


SERIES_IDS = ('cpi', 'core_cpi', 'ppi', 'core_ppi')
OLD_NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
PUBLICATIONS = {
    '2026-09': {'cpi': '2026-10-14T12:30:00Z', 'ppi': '2026-10-15T12:30:00Z'},
    '2026-10': {'cpi': '2026-11-10T13:30:00Z', 'ppi': '2026-11-13T13:30:00Z'},
}


def source_text(mod, observation_month):
    """Successful September CSVs and explicit BLS publication metadata."""
    months = [point for point in indices() if point['month'] <= '2026-09']
    payloads = {}
    for series_id in SERIES_IDS:
        for basis in ('sa', 'nsa'):
            sid = mod.SERIES[series_id][basis]
            payloads[mod.fred_url(sid)] = 'observation_date,' + sid + '\n' + '\n'.join(
                point['month'] + '-01,' + str(point['value']) for point in months
            )
    for group, title in (('cpi', 'CONSUMER PRICE INDEX'), ('ppi', 'PRODUCER PRICE INDEXES')):
        if observation_month == '2026-10':
            release_date = 'Tuesday, November 10, 2026' if group == 'cpi' else 'Friday, November 13, 2026'
            reference = 'OCTOBER 2026'
        else:
            release_date = 'Wednesday, October 14, 2026' if group == 'cpi' else 'Thursday, October 15, 2026'
            reference = 'SEPTEMBER 2026'
        payloads[mod.PUBLICATION_URLS[group]] = (
            '<pre>Transmission of material in this release is embargoed until\n'
            '8:30 a.m. (ET) ' + release_date + '\n' + title + ' - ' + reference + '</pre>'
        )
        payloads[mod.SCHEDULE_URLS[group]] = schedule_html([
            ('November 2026', 'Dec. 10, 2026' if group == 'cpi' else 'Dec. 15, 2026', '08:30 AM')
        ])

    def fetch(url):
        return payloads[url]

    return fetch


def previous_september_cache(mod):
    months = [point for point in indices() if point['month'] <= '2026-09']
    rows = []
    for series_id in SERIES_IDS:
        group = mod.SERIES[series_id]['group']
        rows.append(mod.build_series(
            series_id, months, months, now=OLD_NOW,
            publication={'observationMonth': '2026-09', 'publishedAt': PUBLICATIONS['2026-09'][group]},
        ))
    return {'inflation': {'series': rows}, 'releaseCalendar': {'events': []}}


def october_bls_payload():
    payload = bls_payload()
    for series in payload['Results']['series']:
        latest = deepcopy(series['data'][0])
        latest.update(period='M10', periodName='October', value=str(float(latest['value']) + 1))
        series['data'].insert(0, latest)
    return payload


@pytest.mark.parametrize('series_id', SERIES_IDS)
def test_newer_official_publication_recovers_latest_month_from_bls(series_id):
    mod = generator()
    calls = []

    def fallback(start, end):
        calls.append((start, end))
        return october_bls_payload()

    result = mod.refresh_cache(
        previous_september_cache(mod), now=NOW,
        fetch_text=source_text(mod, '2026-10'), fetch_bls=fallback,
    )
    row = next(row for row in result['inflation']['series'] if row['id'] == series_id)
    assert row['asOf'] == '2026-10'
    assert row['status'] in ('ok', 'partial')
    assert row['source']['saSeriesId'] == mod.BLS_SERIES[series_id]['sa']
    assert row['source']['nsaSeriesId'] == mod.BLS_SERIES[series_id]['nsa']
    assert row['publishedAt'] == PUBLICATIONS['2026-10'][mod.SERIES[series_id]['group']]
    assert row['checkedAt'] == row['collectedAt'] == '2026-11-16T00:00:00Z'
    assert calls == [(2020, 2026)]


@pytest.mark.parametrize('series_id', SERIES_IDS)
@pytest.mark.parametrize('fallback_result', ['stale', 'failed'])
def test_stale_primary_and_unsuitable_bls_preserve_old_verified_row(series_id, fallback_result):
    mod = generator()
    previous = previous_september_cache(mod)
    pristine = deepcopy(previous)
    old = next(row for row in previous['inflation']['series'] if row['id'] == series_id)
    calls = []

    def fallback(start, end):
        calls.append((start, end))
        return bls_payload() if fallback_result == 'stale' else {'status': 'REQUEST_FAILED'}

    result = mod.refresh_cache(
        previous, now=NOW, fetch_text=source_text(mod, '2026-10'), fetch_bls=fallback,
    )
    row = next(row for row in result['inflation']['series'] if row['id'] == series_id)
    assert row['status'] == 'stale'
    for field in ('asOf', 'points', 'sourceIndices', 'publishedAt', 'checkedAt', 'collectedAt'):
        assert row[field] == old[field], field
    assert row.get('staleReason')
    assert calls == [(2020, 2026)]
    assert previous == pristine


def test_matching_september_publication_keeps_september_primary_valid():
    mod = generator()
    previous = previous_september_cache(mod)

    def unexpected_fallback(*args):
        pytest.fail('Matching verified reference month must not trigger BLS fallback')

    result = mod.refresh_cache(
        previous, now=NOW, fetch_text=source_text(mod, '2026-09'), fetch_bls=unexpected_fallback,
    )
    for row in result['inflation']['series']:
        if row['id'] not in SERIES_IDS:
            continue
        assert row['status'] == 'ok'
        assert row['asOf'] == '2026-09'
        assert row['publishedAt'] == PUBLICATIONS['2026-09'][mod.SERIES[row['id']]['group']]
        assert row['checkedAt'] == row['collectedAt'] == '2026-11-16T00:00:00Z'
        assert row['source']['saSeriesId'] == mod.SERIES[row['id']]['sa']
    assert result['inflation']['status'] == 'ok'
