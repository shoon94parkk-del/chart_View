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
MONTHS = {name.lower(): i for i, name in enumerate(('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'), 1)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})


def stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def month_shift(month: str, offset: int) -> str:
    year, number = map(int, month.split('-'))
    value = year * 12 + number - 1 + offset
    return f'{value // 12:04d}-{value % 12 + 1:02d}'


def get_text(url: str) -> str:
    response = requests.get(url, timeout=25, headers={
        'User-Agent': 'ChartView public economic-data cache (BLS/FRED)',
        'Accept': 'text/csv,text/html;q=0.9,*/*;q=0.5',
    })
    response.raise_for_status()
    return response.text


def fred_url(series_id: str) -> str:
    return f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'


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
                 publication: dict | None = None, previous: dict | None = None) -> dict[str, Any]:
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
    return {
        'id': series_id, 'name': meta['name'], 'definition': meta['definition'],
        'unit': '%', 'frequency': 'monthly', 'basis': {'yoy': 'NSA', 'mom': 'SA'},
        'status': 'ok' if complete else 'partial', 'asOf': points[-1]['month'],
        'publishedAt': points[-1]['publishedAt'], 'publicationSourceUrl': PUBLICATION_URLS[meta['group']] if points[-1]['publishedAt'] else None,
        'collectedAt': timestamp, 'checkedAt': timestamp,
        'revisionStatus': 'revised' if revised else 'unknown',
        'revisionCheckedAt': timestamp if previous.get('sourceIndices') else None,
        'revisionNote': 'FRED current vintage. Revised means overlapping index values changed since the prior successful cache; original-release vintage and official revision flags are unavailable.',
        'source': {'name': 'U.S. Bureau of Labor Statistics via FRED',
                   'url': f'https://fred.stlouisfed.org/series/{meta["nsa"]}',
                   'saSeriesId': meta['sa'], 'nsaSeriesId': meta['nsa'],
                   'saUrl': f'https://fred.stlouisfed.org/series/{meta["sa"]}',
                   'nsaUrl': f'https://fred.stlouisfed.org/series/{meta["nsa"]}'},
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
                  fetch_text: Callable[[str], str] = get_text) -> dict[str, Any]:
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
    rows = []
    for series_id, meta in SERIES.items():
        old = old_rows.get(series_id)
        try:
            sa, nsa = (parse_fred_csv(fetched[fred_url(meta[basis])], meta[basis]) for basis in ('sa', 'nsa'))
            if max(sa[-1]['month'], nsa[-1]['month']) >= now.strftime('%Y-%m'):
                raise ValueError('monthly observation is not a completed month')
            row = build_series(series_id, sa, nsa, now=now, publication=publications.get(meta['group']), previous=old)
        except (KeyError, ValueError) as exc:
            errors[series_id] = str(exc)
            if old and old.get('points'):
                row = deepcopy(old)
                row.update(status='stale', staleReason='Official source refresh failed; last verified data retained.')
            else:
                row = {'id': series_id, 'name': meta['name'], 'definition': meta['definition'],
                       'status': 'unavailable', 'asOf': None, 'publishedAt': None,
                       'checkedAt': None, 'collectedAt': None, 'points': []}
        rows.append(row)
    old_calendar = previous.get('releaseCalendar', {})
    old_sources = old_calendar.get('sources', {})
    events, sources, successes = [], {}, 0
    for group, url in SCHEDULE_URLS.items():
        try:
            group_events = parse_schedule(fetched[url], group, now=now)
            sources[group] = {'sourceUrl': url, 'status': 'ok', 'checkedAt': stamp(now)}
            successes += 1
        except (KeyError, ValueError) as exc:
            errors.setdefault(url, str(exc))
            group_events = deepcopy([e for e in old_calendar.get('events', []) if e.get('indicator') == group])
            sources[group] = {'sourceUrl': url, 'status': 'stale' if group_events else 'unavailable',
                              'checkedAt': old_sources.get(group, {}).get('checkedAt')}
        events.extend(group_events)
    events.sort(key=lambda e: (e.get('localDate', ''), e.get('localTime') or '', e['id']))
    calendar_status = 'ok' if successes == 2 else ('partial' if successes else ('stale' if events else 'unavailable'))
    series_status = 'ok' if all(r['status'] == 'ok' for r in rows) else ('unavailable' if all(r['status'] == 'unavailable' for r in rows) else 'partial')
    return {
        'inflation': {'schemaVersion': 1, 'status': series_status, 'generatedAt': stamp(now), 'series': rows},
        'releaseCalendar': {'status': calendar_status, 'checkedAt': stamp(now) if successes == 2 else old_calendar.get('checkedAt'),
                            'sourceUrl': 'https://www.bls.gov/schedule/news_release/', 'sources': sources, 'events': events},
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
