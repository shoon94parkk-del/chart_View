"""Collect official BLS/FRED monthly indexes and confirmed BLS release schedules.

Independent of the existing sixteen macro rows and their summary. Only this
scheduled collector uses providers; the app reads a saved JSON file. YoY uses
NSA indexes and MoM uses SA indexes, matching exact calendar months. FRED is a
current-vintage source, not an original-release or consensus archive.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re
from typing import Any, Callable
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'static' / 'data' / 'inflation_release_cache.json'
EASTERN = ZoneInfo('America/New_York')
SERIES = {
    'cpi': {'name': '미국 CPI', 'definition': '미국 도시 소비자 전체 품목 소비자물가지수(CPI-U)', 'sa': 'CPIAUCSL', 'nsa': 'CPIAUCNS', 'group': 'cpi'},
    'core_cpi': {'name': '미국 근원 CPI', 'definition': '미국 도시 소비자 식품·에너지 제외 소비자물가지수(CPI-U)', 'sa': 'CPILFESL', 'nsa': 'CPILFENS', 'group': 'cpi'},
    'ppi': {'name': '미국 PPI', 'definition': '미국 생산자물가지수 최종수요(Final Demand)', 'sa': 'PPIFIS', 'nsa': 'PPIFID', 'group': 'ppi'},
    'core_ppi': {'name': '미국 근원 PPI', 'definition': '미국 생산자물가지수 최종수요 중 식품·에너지 제외(Final Demand Less Foods and Energy)', 'sa': 'PPIFES', 'nsa': 'PPICOR', 'group': 'ppi'},
}
SCHEDULE_URLS = {key: f'https://www.bls.gov/schedule/news_release/{key}.htm' for key in ('cpi', 'ppi')}
PUBLICATION_URLS = {key: f'https://www.bls.gov/news.release/{key}.nr0.htm' for key in ('cpi', 'ppi')}
BLS_API_URL = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
ICS_URL = 'https://www.bls.gov/schedule/news_release/bls.ics'
BLS_SERIES = {
    'cpi': {'sa': 'CUSR0000SA0', 'nsa': 'CUUR0000SA0'},
    'core_cpi': {'sa': 'CUSR0000SA0L1E', 'nsa': 'CUUR0000SA0L1E'},
    'ppi': {'sa': 'WPSFD4', 'nsa': 'WPUFD4'},
    'core_ppi': {'sa': 'WPSFD49104', 'nsa': 'WPUFD49104'},
}
MONTHS = {name.lower(): i for i, name in enumerate(('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'), 1)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})


def stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def month_shift(month: str, offset: int) -> str:
    year, number = map(int, month.split('-'))
    value = year * 12 + number - 1 + offset
    return f'{value // 12:04d}-{value % 12 + 1:02d}'


def get_text(url: str) -> str:
    if url == ICS_URL:
        request = Request(url, headers={
            'User-Agent': 'ChartView public economic-data cache (BLS/FRED)',
            'Accept': 'text/calendar',
        })
        with urlopen(request, timeout=25) as response:
            return response.read().decode('utf-8-sig')
    response = requests.get(url, timeout=25, headers={
        'User-Agent': 'ChartView public economic-data cache (BLS/FRED)',
        'Accept': 'text/csv,text/html;q=0.9,*/*;q=0.5',
    })
    response.raise_for_status()
    return response.text


def fred_url(series_id: str) -> str:
    return f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'


def fetch_bls_batch(start_year: int, end_year: int) -> dict:
    """One keyless official request; no retries or provider work on API paths."""
    response = requests.post(BLS_API_URL, timeout=25, json={
        'seriesid': [meta[basis] for meta in BLS_SERIES.values() for basis in ('sa', 'nsa')],
        'startyear': str(start_year), 'endyear': str(end_year),
    }, headers={'User-Agent': 'ChartView public economic-data cache (BLS/FRED)', 'Accept': 'application/json'})
    response.raise_for_status()
    return response.json()


def parse_bls_batch(payload: dict) -> dict[str, list[dict]]:
    if not isinstance(payload, dict) or payload.get('status') != 'REQUEST_SUCCEEDED':
        raise ValueError('BLS API did not return REQUEST_SUCCEEDED')
    result = payload.get('Results')
    if not isinstance(result, dict) or not isinstance(result.get('series'), list):
        raise ValueError('BLS API series payload missing')
    allowed = {sid for meta in BLS_SERIES.values() for sid in meta.values()}
    parsed = {}
    for series in result['series']:
        sid = series.get('seriesID') if isinstance(series, dict) else None
        if sid not in allowed:
            continue
        if sid in parsed:
            raise ValueError(f'duplicate BLS series: {sid}')
        values = {}
        data = series.get('data')
        if not isinstance(data, list):
            parsed[sid] = []
            continue
        for point in data:
            if not isinstance(point, dict) or not re.fullmatch(r'M(0[1-9]|1[0-2])', str(point.get('period', ''))):
                continue
            year = str(point.get('year', ''))
            if not re.fullmatch(r'\d{4}', year):
                continue
            month = year + '-' + point['period'][1:]
            if isinstance(point.get('value'), bool):
                continue
            try:
                value = float(point.get('value'))
            except (ValueError, TypeError):
                continue
            if not math.isfinite(value) or value <= 0:
                continue
            if month in values and values[month]['value'] != value:
                raise ValueError(f'conflicting duplicate BLS observation: {month}')
            notes = [{'code': n['code'], 'text': n.get('text')} for n in (point.get('footnotes') or [])
                     if isinstance(n, dict) and n.get('code')]
            values[month] = {'month': month, 'value': value, 'footnotes': notes}
        parsed[sid] = [value for _, value in sorted(values.items())]
    return parsed


def parse_fred_csv(text: str, series_id: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not reader.fieldnames or series_id not in reader.fieldnames:
        raise ValueError(f'missing FRED CSV series column: {series_id}')
    values = {}
    for row in reader:
        raw_date = str(row.get('observation_date') or row.get('DATE') or '')
        try:
            observation = datetime.strptime(raw_date, '%Y-%m-%d')
            value = float(row[series_id])
        except (ValueError, TypeError):
            continue
        if observation.day != 1 or not math.isfinite(value) or value <= 0:
            continue
        month = raw_date[:7]
        if month in values and values[month] != value:
            raise ValueError(f'conflicting duplicate observation: {month}')
        values[month] = value
    if not values:
        raise ValueError(f'no valid FRED monthly indexes: {series_id}')
    return [{'month': month, 'value': value} for month, value in sorted(values.items())]


def build_points(sa: list[dict], nsa: list[dict], *, months: int = 60) -> list[dict[str, Any]]:
    sa_map, nsa_map = ({r['month']: r['value'] for r in rows} for rows in (sa, nsa))
    available = sorted(set(sa_map) | set(nsa_map))
    if not available:
        raise ValueError('no indexes')
    start, end = max(available[0], month_shift(available[-1], 1 - months)), available[-1]
    points = []
    month = start
    while month <= end:
        def change(values: dict, lag: int) -> float | None:
            current, baseline = values.get(month), values.get(month_shift(month, -lag))
            if current is None or baseline is None or baseline <= 0:
                return None
            return round((current / baseline - 1) * 100, 6)
        points.append({'month': month, 'yoy': change(nsa_map, 12), 'mom': change(sa_map, 1), 'publishedAt': None})
        month = month_shift(month, 1)
    return points


def build_series(series_id: str, sa: list[dict], nsa: list[dict], *, now: datetime,
                 publication: dict | None = None, previous: dict | None = None,
                 provider: str = 'fred') -> dict[str, Any]:
    meta, previous = SERIES[series_id], previous or {}
    points = build_points(sa, nsa)
    if not any(p['yoy'] is not None or p['mom'] is not None for p in points):
        raise ValueError('no computable monthly changes')
    if previous.get('asOf') and (min(sa[-1]['month'], nsa[-1]['month']) < previous['asOf']):
        raise ValueError('upstream observation range regressed')
    if previous.get('coverage', {}).get('yoyCount', 0) >= 36 and sum(p['yoy'] is not None for p in points) < 36:
        raise ValueError('upstream historical coverage regressed')
    publications = {p['month']: p['publishedAt'] for p in previous.get('points', []) if p.get('publishedAt')}
    if publication:
        publications[publication['observationMonth']] = publication['publishedAt']
    for point in points:
        point['publishedAt'] = publications.get(point['month'])
    start = month_shift(points[0]['month'], -12)
    source_indices = {basis: [r for r in rows if r['month'] >= start] for basis, rows in (('sa', sa), ('nsa', nsa))}
    revised = False
    for basis, rows in source_indices.items():
        old = {r['month']: r['value'] for r in previous.get('sourceIndices', {}).get(basis, [])}
        revised = revised or any(r['month'] in old and old[r['month']] != r['value'] for r in rows)
    timestamp = stamp(now)
    complete = all(p['mom'] is not None and p['yoy'] is not None for p in points)
    source = {'name': 'U.S. Bureau of Labor Statistics via FRED',
              'url': f'https://fred.stlouisfed.org/series/{meta["nsa"]}',
              'saSeriesId': meta['sa'], 'nsaSeriesId': meta['nsa'],
              'saUrl': f'https://fred.stlouisfed.org/series/{meta["sa"]}',
              'nsaUrl': f'https://fred.stlouisfed.org/series/{meta["nsa"]}'}
    if provider == 'bls':
        bls = BLS_SERIES[series_id]
        source = {'name': 'U.S. Bureau of Labor Statistics Public Data API', 'url': BLS_API_URL,
                  'saSeriesId': bls['sa'], 'nsaSeriesId': bls['nsa'],
                  'saUrl': BLS_API_URL + bls['sa'], 'nsaUrl': BLS_API_URL + bls['nsa']}
        indexes = {'yoy': {r['month']: r for r in nsa}, 'mom': {r['month']: r for r in sa}}
        for point in points:
            point['sourceFootnotes'] = {metric: rows.get(point['month'], {}).get('footnotes', []) for metric, rows in indexes.items()}
    preliminary = any(n.get('code') == 'P' for notes in points[-1].get('sourceFootnotes', {}).values() for n in notes)
    return {
        'id': series_id, 'name': meta['name'],
        'definition': meta['definition'] + (' 최근 값은 잠정치로 추후 수정될 수 있어요.' if preliminary else ''),
        'unit': '%', 'frequency': 'monthly', 'basis': {'yoy': 'NSA', 'mom': 'SA'},
        'status': 'ok' if complete else 'partial', 'asOf': points[-1]['month'],
        'publishedAt': points[-1]['publishedAt'], 'publicationSourceUrl': PUBLICATION_URLS[meta['group']] if points[-1]['publishedAt'] else None,
        'collectedAt': timestamp, 'checkedAt': timestamp,
        'revisionStatus': 'revised' if revised else 'unknown',
        'revisionCheckedAt': timestamp if previous.get('sourceIndices') else None,
        'revisionNote': 'Current source vintage. Revised means overlapping index values changed since the prior successful cache; original-release vintage is unavailable. BLS preliminary footnotes describe observation status, not a detected revision.',
        'observationStatus': 'preliminary' if preliminary else 'unknown',
        'source': source,
        'points': points, 'sourceIndices': source_indices,
        'coverage': {'startMonth': points[0]['month'], 'endMonth': points[-1]['month'], 'months': len(points),
                     'yoyCount': sum(p['yoy'] is not None for p in points), 'momCount': sum(p['mom'] is not None for p in points)},
    }


def parse_named_date(raw: str) -> datetime:
    match = re.fullmatch(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})', raw.strip())
    if not match or match[1].lower() not in MONTHS:
        raise ValueError(f'invalid official date: {raw}')
    return datetime(int(match[3]), MONTHS[match[1].lower()], int(match[2]))


def parse_schedule(html: str, group: str, *, now: datetime) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, 'html.parser')
    table = None
    for candidate in soup.find_all('table'):
        header = candidate.find('tr')
        if header and [c.get_text(' ', strip=True) for c in header.find_all(['td', 'th'])] == ['Reference Month', 'Release Date', 'Release Time']:
            table = candidate
            break
    if table is None:
        raise ValueError('official schedule table not found')
    events = []
    for row in table.find_all('tr')[1:]:
        cells = [c.get_text(' ', strip=True) for c in row.find_all(['td', 'th'])]
        if len(cells) != 3:
            continue
        reference = re.fullmatch(r'([A-Za-z]+)\s+(\d{4})', cells[0])
        if not reference or reference[1].lower() not in MONTHS:
            raise ValueError('invalid official reference month')
        observation_month = f'{int(reference[2]):04d}-{MONTHS[reference[1].lower()]:02d}'
        release = parse_named_date(cells[1])
        local_time, scheduled_at = None, None
        if cells[2]:
            time_match = re.fullmatch(r'(\d{1,2}):(\d{2})\s*(AM|PM)', cells[2], re.I)
            if not time_match:
                raise ValueError('unrecognized official release time')
            hour = int(time_match[1]) % 12 + (12 if time_match[3].upper() == 'PM' else 0)
            release = release.replace(hour=hour, minute=int(time_match[2]), tzinfo=EASTERN)
            local_time, scheduled_at = release.strftime('%H:%M'), stamp(release)
            if release < now:
                continue
        elif release.date() < now.astimezone(EASTERN).date():
            continue
        events.append({'id': f'{group}:{observation_month}', 'indicator': group,
                       'name': '미국 CPI·근원 CPI' if group == 'cpi' else '미국 PPI·근원 PPI',
                       'observationMonth': observation_month, 'scheduledAt': scheduled_at,
                       'localDate': release.strftime('%Y-%m-%d'), 'localTime': local_time,
                       'timeZone': 'America/New_York', 'status': 'confirmed',
                       'sourceUrl': SCHEDULE_URLS[group], 'checkedAt': stamp(now)})
    if not events:
        raise ValueError('official schedule has no future rows')
    return events


def parse_ics_calendar(text: str, *, now: datetime, previous_events: list[dict] | None = None,
                       include_cancelled: bool = False) -> list[dict]:
    """Use explicit ICS times; reference months only survive an exact saved match."""
    text = re.sub(r'\r?\n[ \t]', '', text.lstrip('\ufeff')).replace('\r\n', '\n')
    if not text.startswith('BEGIN:VCALENDAR\n') or text.count('BEGIN:VEVENT') != text.count('END:VEVENT'):
        raise ValueError('invalid official calendar')
    saved = {(e.get('indicator'), e.get('scheduledAt')): e for e in previous_events or [] if e.get('scheduledAt')}
    saved_uids = {(e.get('indicator'), e.get('sourceUid')): e for e in previous_events or [] if e.get('sourceUid')}
    groups = {'Consumer Price Index': 'cpi', 'Producer Price Index': 'ppi'}
    events, seen_uids = [], set()
    for block in re.findall(r'BEGIN:VEVENT\n(.*?)\nEND:VEVENT', text, re.S):
        fields = {}
        for line in block.splitlines():
            key, separator, value = line.partition(':')
            name = key.split(';', 1)[0]
            if separator and name in ('SUMMARY', 'UID', 'DTSTART', 'STATUS'):
                if name in fields:
                    raise ValueError('duplicate official calendar property')
                fields[name] = (key, value)
        group = groups.get(fields.get('SUMMARY', ('', ''))[1])
        if not group:
            continue
        cancelled = fields.get('STATUS', ('', ''))[1] == 'CANCELLED'
        uid = fields.get('UID', ('', ''))[1]
        key, value = fields.get('DTSTART', ('', ''))
        if not uid:
            raise ValueError('official calendar UID unavailable')
        if uid in seen_uids:
            raise ValueError('duplicate official calendar UID')
        seen_uids.add(uid)
        if cancelled and not key:
            # A cancellation identity alone retires a previously known UID.
            local, scheduled, local_time = None, None, None
        elif key == 'DTSTART;VALUE=DATE':
            local = datetime.strptime(value, '%Y%m%d').replace(tzinfo=EASTERN)
            scheduled, local_time = None, None
            if not cancelled and local.date() < now.astimezone(EASTERN).date():
                continue
        else:
            if key == 'DTSTART' and value.endswith('Z'):
                local = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone(EASTERN)
            elif key in ('DTSTART;TZID=US-Eastern', 'DTSTART;TZID=US/Eastern', 'DTSTART;TZID=America/New_York'):
                local = datetime.strptime(value, '%Y%m%dT%H%M%S').replace(tzinfo=EASTERN)
                if (local.utcoffset() != local.replace(fold=1).utcoffset()
                        or local.astimezone(timezone.utc).astimezone(EASTERN).replace(tzinfo=None) != local.replace(tzinfo=None)):
                    raise ValueError('ambiguous or nonexistent official local time')
            else:
                raise ValueError('official calendar timezone unavailable')
            if not cancelled and local <= now:
                continue
            scheduled, local_time = stamp(local), local.strftime('%H:%M')
        old = saved_uids.get((group, uid)) or (saved.get((group, scheduled), {}) if scheduled else {})
        events.append({
            'id': old.get('id') or f'{group}:{uid}', 'indicator': group,
            'name': '미국 CPI·근원 CPI' if group == 'cpi' else '미국 PPI·근원 PPI',
            'observationMonth': old.get('observationMonth'),
            'observationMonthSourceUrl': old.get('observationMonthSourceUrl') or old.get('sourceUrl'),
            'scheduledAt': scheduled, 'localDate': local.strftime('%Y-%m-%d') if local else None, 'localTime': local_time,
            'timeZone': 'America/New_York', 'status': 'cancelled' if cancelled else 'confirmed', 'sourceUrl': ICS_URL,
            'sourceUid': uid, 'checkedAt': stamp(now),
        })
    if not events:
        raise ValueError('official calendar has no future CPI/PPI entries')
    visible = events if include_cancelled else [e for e in events if e['status'] == 'confirmed']
    return sorted(visible, key=lambda e: (e['localDate'] or '', e['localTime'] or '', e['id']))


def parse_publication(html: str, group: str) -> dict[str, str]:
    text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    title = 'CONSUMER PRICE INDEX' if group == 'cpi' else 'PRODUCER PRICE INDEXES?'
    observation = re.search(title + r'\s*[-–]\s*([A-Za-z]+)\s+(\d{4})', text, re.I)
    release = re.search(r'(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*\(ET\)\s+\w+,?\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', text, re.I)
    if not observation or not release or observation[1].lower() not in MONTHS:
        raise ValueError('official publication month or release timestamp unavailable')
    instant = parse_named_date(release[4]).replace(hour=int(release[1]) % 12 + (12 if release[3].lower() == 'p' else 0), minute=int(release[2]), tzinfo=EASTERN)
    return {'observationMonth': f'{int(observation[2]):04d}-{MONTHS[observation[1].lower()]:02d}',
            'publishedAt': stamp(instant), 'sourceUrl': PUBLICATION_URLS[group]}


def refresh_cache(previous: dict | None = None, *, now: datetime | None = None,
                  fetch_text: Callable[[str], str] = get_text,
                  fetch_bls: Callable[[int, int], dict] | None = None) -> dict[str, Any]:
    now, previous = now or datetime.now(timezone.utc), previous or {}
    urls = {fred_url(meta[basis]) for meta in SERIES.values() for basis in ('sa', 'nsa')}
    urls.update(SCHEDULE_URLS.values())
    urls.update(PUBLICATION_URLS.values())
    fetched, errors = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_text, url): url for url in sorted(urls)}
        for future in as_completed(futures):
            url = futures[future]
            try:
                fetched[url] = future.result()
            except Exception as exc:
                errors[url] = str(exc)
    publications = {}
    for group, url in PUBLICATION_URLS.items():
        try:
            publications[group] = parse_publication(fetched[url], group)
            if publications[group]['publishedAt'] > stamp(now):
                raise ValueError('publication timestamp is in the future')
        except (KeyError, ValueError) as exc:
            publications.pop(group, None)
            errors.setdefault(url, str(exc))
    old_rows = {r['id']: r for r in previous.get('inflation', {}).get('series', [])}
    rows, failed = {}, []

    def validated(series_id: str, sa: list, nsa: list, provider: str) -> dict:
        if not sa or not nsa:
            raise ValueError('official index pair incomplete')
        if max(sa[-1]['month'], nsa[-1]['month']) >= now.strftime('%Y-%m'):
            raise ValueError('monthly observation is not a completed month')
        row = build_series(series_id, sa, nsa, now=now, publication=publications.get(SERIES[series_id]['group']),
                           previous=old_rows.get(series_id), provider=provider)
        if provider == 'bls' and (len(row['points']) != 60 or row['coverage']['yoyCount'] < 36):
            raise ValueError('BLS fallback did not retain required history')
        return row

    for series_id, meta in SERIES.items():
        try:
            sa, nsa = (parse_fred_csv(fetched[fred_url(meta[basis])], meta[basis]) for basis in ('sa', 'nsa'))
            rows[series_id] = validated(series_id, sa, nsa, 'fred')
        except (KeyError, ValueError) as exc:
            failed.append(series_id)
            errors[series_id] = str(exc)
    if failed:
        try:
            bls_payload = (fetch_bls or fetch_bls_batch)(now.year - 6, now.year)
            indexes = parse_bls_batch(bls_payload)
        except Exception as exc:
            errors[BLS_API_URL] = str(exc)
            indexes = {}
        for series_id in failed:
            try:
                meta = BLS_SERIES[series_id]
                row = validated(series_id, indexes[meta['sa']], indexes[meta['nsa']], 'bls')
                # Preserve official missing-value footnotes as well as finite-index notes.
                gaps = {}
                for basis in ('sa', 'nsa'):
                    raw = next(s for s in bls_payload['Results']['series'] if isinstance(s, dict) and s.get('seriesID') == meta[basis])
                    known = {r['month'] for r in indexes[meta[basis]]}
                    gaps[basis] = [{'month': str(p.get('year')) + '-' + str(p.get('period'))[1:],
                                    'value': p.get('value'), 'footnotes': p.get('footnotes', [])}
                                   for p in raw.get('data', []) if isinstance(p, dict)
                                   and re.fullmatch(r'\d{4}', str(p.get('year', '')))
                                   and re.fullmatch(r'M(0[1-9]|1[0-2])', str(p.get('period', '')))
                                   and str(p.get('year')) + '-' + p['period'][1:] not in known]
                row['sourceGaps'] = gaps
                rows[series_id] = row
                errors.pop(series_id, None)
            except (KeyError, ValueError, StopIteration) as exc:
                errors[series_id] = str(exc)
    for series_id, meta in SERIES.items():
        if series_id in rows:
            continue
        old = old_rows.get(series_id)
        if old and old.get('points'):
            row = deepcopy(old)
            row.update(status='stale', staleReason='Official source refresh failed; last verified data retained.')
        else:
            row = {'id': series_id, 'name': meta['name'], 'definition': meta['definition'],
                   'status': 'unavailable', 'asOf': None, 'publishedAt': None,
                   'checkedAt': None, 'collectedAt': None, 'points': []}
        rows[series_id] = row

    old_calendar = previous.get('releaseCalendar', {})
    old_sources = old_calendar.get('sources', {})
    events_by_group, sources, failed_groups = {}, {}, []
    for group, url in SCHEDULE_URLS.items():
        try:
            events_by_group[group] = parse_schedule(fetched[url], group, now=now)
            sources[group] = {'sourceUrl': url, 'status': 'ok', 'checkedAt': stamp(now)}
        except (KeyError, ValueError) as exc:
            errors.setdefault(url, str(exc))
            failed_groups.append(group)
            events_by_group[group] = deepcopy([e for e in old_calendar.get('events', []) if e.get('indicator') == group])
            sources[group] = {'sourceUrl': url, 'status': 'stale' if events_by_group[group] else 'unavailable',
                              'checkedAt': old_sources.get(group, {}).get('checkedAt')}
    ics_events = []
    if failed_groups:
        try:
            ics_events = parse_ics_calendar(fetch_text(ICS_URL), now=now, previous_events=old_calendar.get('events', []), include_cancelled=True)
        except Exception as exc:
            errors[ICS_URL] = str(exc)
            ics_events = []
        for group in failed_groups:
            signals = [e for e in ics_events if e['indicator'] == group]
            if not signals:
                continue
            fresh = [e for e in signals if e['status'] == 'confirmed']
            confirmed = {(e['scheduledAt'], e['localDate']) for e in signals if e['localDate']}
            confirmed_uids = {e['sourceUid'] for e in signals}
            # Release-date calendar months bound the uncertain HTML seed rows
            # to suppress; they never supply an observation/reference month.
            covered_months = {e['localDate'][:7] for e in signals if e['localDate']}
            retained = [e for e in events_by_group[group]
                        if (e.get('scheduledAt'), e.get('localDate')) not in confirmed
                        and e.get('sourceUid') not in confirmed_uids
                        and not (not e.get('sourceUid') and str(e.get('localDate', ''))[:7] in covered_months)]
            for event in retained:
                event['checkStatus'] = 'stale'
            events_by_group[group] = fresh + retained
            sources[group] = {'sourceUrl': ICS_URL, 'status': 'partial' if retained else 'ok',
                              'checkedAt': stamp(now), 'freshEventCount': len(fresh), 'retainedEventCount': len(retained),
                              'cancelledEventCount': sum(e['status'] == 'cancelled' for e in signals)}
    events = [e for group in SCHEDULE_URLS for e in events_by_group[group]]
    events.sort(key=lambda e: (e.get('localDate', ''), e.get('localTime') or '', e['id']))
    complete_calendar = all(s['status'] == 'ok' for s in sources.values())
    successes = sum(s['status'] in ('ok', 'partial') for s in sources.values())
    calendar_status = 'ok' if complete_calendar else ('partial' if successes else ('stale' if events else 'unavailable'))
    ordered = [rows[series_id] for series_id in SERIES]
    series_status = 'ok' if all(r['status'] == 'ok' for r in ordered) else ('unavailable' if all(r['status'] == 'unavailable' for r in ordered) else 'partial')
    return {
        'inflation': {'schemaVersion': 1, 'status': series_status, 'generatedAt': stamp(now), 'series': ordered},
        'releaseCalendar': {'status': calendar_status, 'checkedAt': stamp(now) if complete_calendar else old_calendar.get('checkedAt'),
                            'sourceUrl': ICS_URL if ics_events else 'https://www.bls.gov/schedule/news_release/',
                            'sources': sources, 'events': events},
        'generatedAt': stamp(now), 'errors': errors,
    }


def main() -> None:
    try:
        previous = json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previous = {}
    result = refresh_cache(previous)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    temporary.replace(OUT)
    print('inflation:', result['inflation']['status'], 'calendar:', result['releaseCalendar']['status'], 'errors:', len(result['errors']))
    for row in result['inflation']['series']:
        print(row['id'], row['status'], row.get('asOf'), row.get('coverage', {}))


if __name__ == '__main__':
    main()
