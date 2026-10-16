"""Bounded keyless BEA inputs for the optional PCE release cache.

The workbook's monthly indices are SA for both YoY and MoM. Parsing does not
invent a release time from its date-only publication metadata. No app requests
should call providers; this module is for the scheduled cache collector.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import io
import json
import math
import posixpath
import re
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

import requests

WORKBOOK_URL = 'https://apps.bea.gov/national/Release/XLS/Underlying/Section2All_xls.xlsx'
PRODUCT_URL = 'https://www.bea.gov/data/personal-consumption-expenditures-price-index'
RELEASE_DATES_URL = 'https://apps.bea.gov/API/signup/release_dates.json'
TABLE = 'Table 2.3.4U. Price Indexes for Personal Consumption Expenditures by Major Type of Product and by Major Function'
ACCOUNTS = {'pce': 'DPCERG', 'core_pce': 'DPCCRG'}
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
MONTHS = {name.lower(): i for i, name in enumerate(('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'), 1)}


def _month_number(month: str) -> int:
    year, number = map(int, month.split('-'))
    return year * 12 + number - 1


def _date(raw: str) -> datetime:
    match = re.fullmatch(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', raw.strip())
    if not match or match[1].lower() not in MONTHS:
        raise ValueError('invalid BEA publication date')
    return datetime(int(match[3]), MONTHS[match[1].lower()], int(match[2]))


def parse_pce_workbook(content: bytes, *, minimum_months: int = 72) -> dict:
    """Resolve the official monthly table and account codes without Excel deps."""
    if not isinstance(content, bytes) or len(content) > 32 * 1024 * 1024:
        raise ValueError('invalid or oversized BEA workbook')
    if minimum_months < 2:
        raise ValueError('minimum_months must be at least two')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as book:
            def xml(name):
                if book.getinfo(name).file_size > 64 * 1024 * 1024:
                    raise ValueError('oversized BEA workbook member')
                return ET.fromstring(book.read(name))
            strings = [''.join(s.itertext()) for s in xml('xl/sharedStrings.xml').findall('m:si', NS)] if 'xl/sharedStrings.xml' in book.namelist() else []
            sheets = [s for s in xml('xl/workbook.xml').findall('m:sheets/m:sheet', NS) if s.attrib.get('name') == 'U20304-M']
            if len(sheets) != 1:
                raise ValueError('BEA monthly PCE worksheet missing or duplicated')
            rid = sheets[0].attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            targets = [r.attrib['Target'] for r in xml('xl/_rels/workbook.xml.rels') if r.attrib.get('Id') == rid and r.attrib.get('TargetMode') != 'External']
            if len(targets) != 1:
                raise ValueError('BEA worksheet relationship unavailable')
            target = posixpath.normpath(targets[0].lstrip('/') if targets[0].startswith('/') else 'xl/' + targets[0])
            if not target.startswith('xl/worksheets/'):
                raise ValueError('invalid BEA worksheet target')
            rows = []
            for row in xml(target).findall('m:sheetData/m:row', NS):
                values = {}
                for c in row.findall('m:c', NS):
                    address = c.attrib.get('r', '')
                    if not re.fullmatch(r'[A-Z]+[1-9]\d*', address) or address in values:
                        raise ValueError('invalid or duplicate BEA cell')
                    val = c.find('m:v', NS)
                    value = val.text if val is not None and val.text is not None else ''
                    if c.attrib.get('t') == 's':
                        value = strings[int(value)]
                    elif c.attrib.get('t') == 'inlineStr':
                        value = ''.join(c.find('m:is', NS).itertext())
                    values[address] = value
                rows.append(values)
    except (zipfile.BadZipFile, KeyError, IndexError, ET.ParseError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError('invalid BEA XLSX workbook') from exc
    text = [v for row in rows for v in row.values()]
    if TABLE not in text:
        raise ValueError('unexpected BEA PCE table title')
    if not any('2017=100' in value and 'quarters and months are seasonally adjusted' in value.lower() and 'not seasonally adjusted' not in value.lower() for value in text):
        raise ValueError('BEA monthly SA index metadata unavailable')
    dates = [_date(v[len('Data published '):]).date().isoformat() for v in text if v.startswith('Data published ')]
    if len(set(dates)) != 1:
        raise ValueError('BEA publication date unavailable or conflicting')
    headers = [row for row in rows if sum(bool(re.fullmatch(r'\d{4}M(?:0[1-9]|1[0-2])', v)) for v in row.values()) >= minimum_months]
    if len(headers) != 1:
        raise ValueError('BEA monthly headers unavailable or duplicated')
    columns = {re.sub(r'\d+$', '', cell): value[:4] + '-' + value[5:] for cell, value in headers[0].items() if re.fullmatch(r'\d{4}M(?:0[1-9]|1[0-2])', value)}
    months = list(columns.values())
    if len(set(months)) != len(months):
        raise ValueError('duplicate BEA observation month')
    months.sort()
    if any(_month_number(b) - _month_number(a) != 1 for a, b in zip(months, months[1:])):
        raise ValueError('incomplete BEA monthly coverage')
    series = {}
    for sid, code in ACCOUNTS.items():
        matches = [row for row in rows if code in row.values()]
        if not matches:
            raise ValueError('BEA account code missing: ' + code)
        candidates = []
        for row in matches:
            values = {re.sub(r'\d+$', '', cell): value for cell, value in row.items()}
            points = []
            for column, month in columns.items():
                try:
                    value = float(values[column])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError('missing BEA monthly index') from exc
                if not math.isfinite(value) or value <= 0:
                    raise ValueError('invalid BEA monthly index')
                points.append({'month': month, 'value': round(value, 3)})
            candidates.append(sorted(points, key=lambda p: p['month']))
        # BEA repeats headline PCE in the product and function sections.
        if any(points != candidates[0] for points in candidates[1:]):
            raise ValueError('conflicting duplicate BEA account: ' + code)
        series[sid] = candidates[0]
    return {'series': series, 'observationMonth': months[-1], 'publishedDate': dates[0],
            'publicationPrecision': 'day', 'basis': 'SA', 'indexBase': '2017=100',
            'sourceUrl': WORKBOOK_URL, 'table': TABLE, 'beaAccountCodes': dict(ACCOUNTS)}


def download_pce_workbook() -> bytes:
    """Bound the transfer while preserving requests proxy and TLS defaults."""
    limit = 32 * 1024 * 1024
    response = requests.get(WORKBOOK_URL, timeout=25, stream=True, headers={
        'User-Agent': 'ChartView public economic-data cache (BEA)',
        'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    try:
        response.raise_for_status()
        size = response.headers.get('Content-Length', '')
        if size.isdigit() and int(size) > limit:
            raise ValueError('BEA workbook download exceeds size limit')
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            if len(content) + len(chunk) > limit:
                raise ValueError('BEA workbook download exceeds size limit')
            content.extend(chunk)
        return bytes(content)
    finally:
        response.close()


def fetch_pce_indices() -> dict:
    """One bounded official workbook request, preserving requests proxy/TLS defaults."""
    return parse_pce_workbook(download_pce_workbook())


def parse_bea_release_dates(payload: dict | str, *, now: datetime) -> list[str]:
    """Return confirmed future PIO instants only; the JSON has no reference month."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('calendar now must include timezone')
    if isinstance(payload, str):
        payload = json.loads(payload)
    group = payload.get('Personal Income and Outlays') if isinstance(payload, dict) else None
    raw_dates = group.get('release_dates') if isinstance(group, dict) else None
    if not isinstance(raw_dates, list):
        raise ValueError('BEA Personal Income and Outlays schedule unavailable')
    dates = set()
    for raw in raw_dates:
        try:
            instant = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError('invalid BEA scheduled timestamp') from exc
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('BEA scheduled timestamp missing timezone')
        if instant >= now:
            dates.add(instant.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'))
    return sorted(dates)


class _Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.text, self.headings, self.anchors = [], [], []
        self.in_h1, self.anchor = False, None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'h1':
            self.in_h1 = True
        if tag == 'a':
            self.anchor = {'href': dict(attrs).get('href', ''), 'text': []}

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.in_h1 = False
        if tag == 'a' and self.anchor is not None:
            self.anchors.append(self.anchor)
            self.anchor = None

    def handle_data(self, data):
        self.text.append(data)
        if self.in_h1:
            self.headings.append(data)
        if self.anchor is not None:
            self.anchor['text'].append(data)


def _official_publication_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'www.bea.gov' or not re.fullmatch(r'/news/\d{4}/personal-income-and-outlays-[a-z]+-\d{4}', parsed.path) or parsed.query or parsed.fragment:
        raise ValueError('unverified BEA publication URL')
    return url


def current_pce_release_url(product_page_html: str) -> str:
    matches = {_official_publication_url(urljoin(PRODUCT_URL, a['href'])) for a in _Document(product_page_html).anchors if ' '.join(' '.join(a['text']).split()).lower() == 'current release'}
    if len(matches) != 1:
        raise ValueError('current BEA PCE publication link unavailable or conflicting')
    return matches.pop()


def parse_pce_publication(news_html: str, *, source_url: str) -> dict:
    """Use only an explicit official embargo timestamp, never an assumed time."""
    source_url = _official_publication_url(source_url)
    document = _Document(news_html)
    heading = ' '.join(document.headings)
    observation = re.search(r'Personal Income and Outlays,\s*([A-Za-z]+)\s+(\d{4})', heading)
    text = ' '.join(' '.join(document.text).split())
    release = re.search(r'EMBARGOED UNTIL RELEASE AT\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s+(EDT|EST),?\s+(?:[A-Za-z]+,?\s+)?([A-Za-z]+\s+\d{1,2},\s+\d{4})', text, re.I)
    if not observation or observation[1].lower() not in MONTHS or not release:
        raise ValueError('explicit BEA publication month or timestamp unavailable')
    hour, minute = int(release[1]), int(release[2])
    if not 1 <= hour <= 12 or minute > 59:
        raise ValueError('invalid BEA publication time')
    instant = _date(release[5]).replace(hour=hour % 12 + (12 if release[3].lower() == 'p' else 0), minute=minute, tzinfo=ZoneInfo('America/New_York'))
    if instant.tzname() != release[4].upper():
        raise ValueError('conflicting BEA publication timezone')
    return {'observationMonth': f'{observation[2]}-{MONTHS[observation[1].lower()]:02d}',
            'publishedAt': instant.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'publishedDate': instant.date().isoformat(), 'publicationPrecision': 'second', 'sourceUrl': source_url}
