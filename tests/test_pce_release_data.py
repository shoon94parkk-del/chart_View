"""Small XLSX fixtures exercise the official BEA workbook's actual layout."""
from datetime import datetime, timezone
import importlib
import io
import json
from xml.sax.saxutils import escape
import zipfile

import pytest


def mod():
    return importlib.import_module('scripts.pce_release_data')


def workbook(*, basis='[Index numbers, 2017=100; quarters and months are seasonally adjusted]', months=72, missing_month=False, duplicate_code=False, bad_value=False, duplicate_month=False):
    def column(n):
        out = ''
        while n:
            n, r = divmod(n - 1, 26)
            out = chr(65 + r) + out
        return out
    labels = []
    for i in range(months):
        index = 2020 * 12 + 8 + i
        labels.append(f'{index // 12}M{index % 12 + 1:02d}')
    if missing_month:
        labels[30] = '2023M04'
    if duplicate_month:
        labels[30] = labels[29]
    strings = [
        'Table 2.3.4U. Price Indexes for Personal Consumption Expenditures by Major Type of Product and by Major Function',
        basis, 'Monthly data from 2020M09 to 2026M08', 'Bureau of Economic Analysis',
        'Data published September 30, 2026', 'File created Sep 29 2026  5:00AM',
        'Personal consumption expenditures (PCE)', 'DPCERG', 'PCE excluding food and energy', 'DPCCRG',
    ] + labels
    def text(c, i):
        return f'<c r="{c}" t="s"><v>{i}</v></c>'
    rows = [f'<row r="{i + 1}">{text(f"A{i + 1}", i)}</row>' for i in range(6)]
    rows.append('<row r="12">' + ''.join(text(f'{column(i + 4)}12', i + 10) for i in range(months)) + '</row>')
    for row_number, label_index, code_index, base in [(15, 6, 7, 100), (42, 8, 9, 110)]:
        values = [f'<c r="{column(i + 4)}{row_number}"><v>{"0" if bad_value and i == 5 else base + i / 10}</v></c>' for i in range(months)]
        rows.append(f'<row r="{row_number}">{text(f"B{row_number}", label_index)}{text(f"C{row_number}", code_index)}' + ''.join(values) + '</row>')
    if duplicate_code:
        rows.append('<row r="60">' + text('C60', 7) + '</row>')
    files = {
        'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="U20304-M" sheetId="9" r:id="rId9"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId9" Target="worksheets/sheet9.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
        'xl/sharedStrings.xml': '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + ''.join(f'<si><t>{escape(s)}</t></si>' for s in strings) + '</sst>',
        'xl/worksheets/sheet9.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(rows) + '</sheetData></worksheet>',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return output.getvalue()


def test_workbook_resolves_sheet_accounts_and_calendar_months():
    result = mod().parse_pce_workbook(workbook())
    assert set(result['series']) == {'pce', 'core_pce'}
    assert result['series']['pce'][0] == {'month': '2020-09', 'value': 100.0}
    assert result['series']['core_pce'][-1] == {'month': '2026-08', 'value': 117.1}
    assert len(result['series']['pce']) == 72
    assert result['basis'] == 'SA'
    assert result['indexBase'] == '2017=100'
    assert result['publishedDate'] == '2026-09-30'
    assert result['publicationPrecision'] == 'day'
    assert not result.get('publishedAt')
    assert result['observationMonth'] == '2026-08'
    assert result['beaAccountCodes'] == {'pce': 'DPCERG', 'core_pce': 'DPCCRG'}


@pytest.mark.parametrize('options', [
    {'basis': '[Index numbers, 2017=100; not seasonally adjusted]'},
    {'basis': '[Index numbers, 2012=100; quarters and months are seasonally adjusted]'},
    {'months': 71}, {'missing_month': True}, {'duplicate_month': True},
    {'duplicate_code': True}, {'bad_value': True},
])
def test_invalid_or_incomplete_official_workbook_is_rejected(options):
    with pytest.raises(ValueError):
        mod().parse_pce_workbook(workbook(**options))


def test_html_200_is_not_treated_as_an_excel_workbook():
    with pytest.raises(ValueError):
        mod().parse_pce_workbook(b'<html>BEA data application</html>')


def test_workbook_fetch_is_one_bounded_verified_request(monkeypatch):
    calls = []
    class Response:
        headers = {}
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size):
            yield workbook()
        def close(self):
            pass
    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr(mod().requests, 'get', fetch)
    result = mod().fetch_pce_indices()
    assert result['observationMonth'] == '2026-08'
    assert len(calls) == 1
    assert calls[0][0] == mod().WORKBOOK_URL
    assert calls[0][1]['timeout'] == 25
    assert calls[0][1].get('verify', True) is True
    assert 'proxies' not in calls[0][1]


def test_release_dates_are_future_confirmed_utc_without_reference_months():
    payload = {'Personal Income and Outlays': {'release_dates': ['2026-09-30T12:30:00+00:00', '2026-10-29T08:30:00-04:00', '2026-10-29T12:30:00+00:00', '2026-11-25T13:30:00+00:00']}, 'Gross Domestic Product': {'release_dates': ['2026-10-25T12:30:00+00:00']}}
    result = mod().parse_bea_release_dates(json.dumps(payload), now=datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert result == ['2026-10-29T12:30:00Z', '2026-11-25T13:30:00Z']


@pytest.mark.parametrize('payload', [{}, {'Personal Income and Outlays': {'release_dates': ['2026-10-29T08:30:00']}}])
def test_release_dates_reject_missing_group_and_naive_times(payload):
    with pytest.raises(ValueError):
        mod().parse_bea_release_dates(payload, now=datetime(2026, 10, 16, tzinfo=timezone.utc))


def test_current_release_url_is_read_from_official_link():
    assert mod().current_pce_release_url('<a href="/news/2026/personal-income-and-outlays-august-2026">Current Release</a>') == 'https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026'
    with pytest.raises(ValueError):
        mod().current_pce_release_url('<a href="https://example.com/news/2026/personal-income-and-outlays-august-2026">Current Release</a>')


def test_explicit_publication_time_is_used_and_file_time_is_never_invented():
    source = 'https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026'
    html = '<h1>Personal Income and Outlays, August 2026</h1><p>EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Wednesday, September 30, 2026</p>'
    result = mod().parse_pce_publication(html, source_url=source)
    assert result['publishedAt'] == '2026-09-30T12:30:00Z'
    assert result['observationMonth'] == '2026-08'
    assert result['publicationPrecision'] == 'second'
    with pytest.raises(ValueError):
        mod().parse_pce_publication('<h1>Personal Income and Outlays, August 2026</h1><p>File created Sep 29 2026 5:00AM</p>', source_url=source)


def test_identical_repeated_account_in_product_and_function_sections_is_allowed():
    original = workbook()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            if name == 'xl/worksheets/sheet9.xml':
                xml = data.decode()
                start, end = xml.index('<row r="15">'), xml.index('</row>', xml.index('<row r="15">')) + len('</row>')
                repeated = xml[start:end].replace('15"', '60"')
                data = xml.replace('</sheetData>', repeated + '</sheetData>').encode()
            target.writestr(name, data)
    assert mod().parse_pce_workbook(output.getvalue())['series']['pce'] == mod().parse_pce_workbook(original)['series']['pce']
