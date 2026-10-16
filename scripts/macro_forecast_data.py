"""Bounded, opt-in forecast receipt import and provider-free cache validation.

Trading Economics mappings use its documented calendar schema only. No event
IDs, category mappings, credentials, network client or scheduled job are built
in. A caller must supply licensed raw bytes and an explicit event mapping.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

CACHE_PATH = Path(__file__).resolve().parents[1] / 'static/data/macro_forecast_cache.json'
MAX_BYTES = 2_000_000
MAX_ROWS = 2_000
BASIS = {sid: {'yoy': 'SA' if sid in ('pce', 'core_pce') else 'NSA', 'mom': 'SA'}
         for sid in ('cpi', 'core_cpi', 'ppi', 'core_ppi', 'pce', 'core_pce')}
PROVIDER = 'Trading Economics'


def instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or 'T' not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def safe_url(value: Any) -> bool:
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        return False
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        if url.scheme != 'https' or url.username or url.password or url.fragment or url.port not in (None, 443):
            return False
        if not host or '.' not in host or host.endswith(('.local', '.internal', '.localhost')):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        # Evidence links are public documents, never authenticated API URLs.
        # No query parameters are currently required by this contract.
        return not url.query
    except ValueError:
        return False


def number(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def decode_json(raw: bytes) -> Any:
    """Reject ambiguous/nonstandard JSON and contain bounded decoder failures."""
    def unique_fields(pairs: list[tuple]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON field')
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError('nonfinite JSON constant')

    try:
        return json.loads(raw, object_pairs_hook=unique_fields, parse_constant=reject_constant)
    except RecursionError as error:
        raise ValueError('JSON nesting depth exceeded') from error


def receipt_key(row: Any) -> tuple | None:
    if not isinstance(row, dict):
        return None
    parts = tuple(row.get(key) for key in ('seriesId', 'month', 'rate', 'basis', 'unit'))
    return parts if all(isinstance(part, str) for part in parts) else None


def valid_identity(row: dict) -> bool:
    sid, month, rate = row.get('seriesId'), row.get('month'), row.get('rate')
    return (isinstance(sid, str) and sid in BASIS and isinstance(rate, str) and rate in BASIS[sid]
            and isinstance(month, str) and bool(re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month))
            and row.get('basis') == BASIS[sid][rate] and row.get('unit') == '%')


def archive_valid(row: dict, now: datetime) -> bool:
    archive = row.get('archive')
    retrieved = instant(row.get('retrievedAt'))
    return (retrieved is not None and retrieved <= now and isinstance(archive, dict)
            and safe_url(archive.get('url')) and isinstance(archive.get('eventId'), str)
            and bool(archive['eventId'].strip()) and len(archive['eventId']) <= 200
            and isinstance(archive.get('contentSha256'), str)
            and bool(re.fullmatch(r'[0-9a-fA-F]{64}', archive['contentSha256'])))


def forecast_valid(row: dict, now: datetime) -> bool:
    if not valid_identity(row) or not number(row.get('expected')):
        return False
    source = row.get('source')
    if not isinstance(source, dict) or not isinstance(source.get('forecastName'), str) or not source['forecastName'].strip() or not safe_url(source.get('forecastUrl')):
        return False
    kind = row.get('evidenceKind')
    if kind == 'provider_archive':
        return archive_valid(row, now)
    if kind not in (None, '', 'captured_before', 'pre_release_capture'):
        return False
    published, captured, available = (instant(row.get(key)) for key in ('publishedAt', 'forecastCapturedAt', 'forecastPublishedAt'))
    return all(t is not None for t in (published, captured, available)) and available <= captured < published <= now


def comparison_valid(receipt: dict, series: dict, now: datetime) -> bool:
    if not forecast_valid(receipt, now) or not number(receipt.get('actual')) or receipt.get('actualVintage') != 'first_release':
        return False
    published = instant(receipt.get('publishedAt'))
    source = receipt.get('source', {})
    if not published or published > now or not safe_url(source.get('actualUrl')):
        return False
    try:
        local_release = published.astimezone(ZoneInfo('America/New_York'))
    except (OverflowError, ValueError):
        return False
    release_month = f'{local_release.year:04d}-{local_release.month:02d}'
    if release_month <= receipt['month']:
        return False
    # A provider's latest Actual is never promoted here. Comparisons require a
    # separately supplied official receipt and its release date/time.
    expected_host = 'bea.gov' if receipt['seriesId'] in ('pce', 'core_pce') else 'bls.gov'
    actual_url = urlsplit(source['actualUrl'])
    if actual_url.hostname not in (expected_host, 'www.' + expected_host) or not actual_url.path.strip('/'):
        return False
    point = next((p for p in series.get('points', []) if isinstance(p, dict) and p.get('month') == receipt['month']), {})
    known = point.get('publishedAt') or (series.get('publishedAt') if receipt['month'] == series.get('asOf') else None)
    if known and (instant(known) is None or instant(known) != published):
        return False
    known_date = point.get('publishedDate') or (series.get('publishedDate') if receipt['month'] == series.get('asOf') else None)
    # Unknown timing is an evidence gap, never permission to trust a vendor
    # first-release label. Verified saved official metadata must corroborate it.
    if not known and not known_date:
        return False
    return not known_date or local_release.date().isoformat() == known_date


def empty_cache(status: str = 'not_configured') -> dict:
    return {'schemaVersion': 1, 'provider': PROVIDER, 'status': status, 'checkedAt': None,
            'forecasts': [], 'comparisons': []}


def load_cache(path: Path | None = None) -> dict:
    try:
        with (path or CACHE_PATH).open('rb') as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return empty_cache('unavailable')
        data = decode_json(raw)
        if (not isinstance(data, dict) or data.get('schemaVersion') != 1
                or not isinstance(data.get('provider'), str) or not data['provider'].strip()
                or not all(isinstance(data.get(key), list) and len(data[key]) <= MAX_ROWS for key in ('forecasts', 'comparisons'))
                or data.get('status') not in ('ok', 'partial', 'not_configured', 'unavailable')):
            return empty_cache('unavailable')
        return data
    except FileNotFoundError:
        return empty_cache()
    except (OSError, ValueError, TypeError):
        return empty_cache('unavailable')


def same_forecast(left: dict, right: dict) -> bool:
    """Both arrays describe one survey vintage for a given receipt identity."""
    keys = ('expected', 'retrievedAt', 'forecastPublishedAt', 'forecastCapturedAt')
    if any(left.get(key) != right.get(key) for key in keys):
        return False
    legacy_kinds = (None, '', 'captured_before', 'pre_release_capture')
    left_kind, right_kind = left.get('evidenceKind'), right.get('evidenceKind')
    if left_kind != right_kind and not (left_kind in legacy_kinds and right_kind in legacy_kinds):
        return False
    if left.get('archive') != right.get('archive'):
        return False
    return all(left['source'].get(key) == right['source'].get(key)
               for key in ('forecastName', 'forecastUrl'))


def attach_forecasts(inflation: dict, cache: dict, *, now: datetime) -> None:
    """Attach validated copies to six existing rows; never change saved rates."""
    enabled = cache.get('status') in ('ok', 'partial')
    counts = {key: Counter(receipt_key(r) for r in cache.get(key, []) if receipt_key(r)) for key in ('forecasts', 'comparisons')}
    totals = {'forecastCount': 0, 'comparisonCount': 0}
    invalid = False
    for series in inflation.get('series', []):
        if not isinstance(series, dict) or series.get('id') not in BASIS:
            continue
        matched = {'forecasts': [], 'comparisons': []}
        row_invalid = False
        months = {p.get('month') for p in series.get('points', []) if isinstance(p, dict) and isinstance(p.get('month'), str)}
        months.add(series.get('asOf'))
        legacy = series.get('comparisons', [])
        legacy = legacy if isinstance(legacy, list) else []
        for kind in matched:
            for receipt in cache.get(kind, []) if enabled else []:
                if not isinstance(receipt, dict) or receipt.get('seriesId') != series['id']:
                    continue
                key = receipt_key(receipt)
                valid = (key is not None and counts[kind][key] == 1 and receipt.get('month') in months
                         and series.get('basis', {}).get(receipt.get('rate')) == receipt.get('basis')
                         and series.get('unit') == receipt.get('unit') and forecast_valid(receipt, now))
                if kind == 'comparisons':
                    valid = valid and comparison_valid(receipt, series, now) and not any(
                        isinstance(old, dict) and all(old.get(k) == receipt.get(k) for k in ('month', 'rate')) for old in legacy)
                if valid:
                    matched[kind].append(receipt)
                else:
                    row_invalid = invalid = True
        conflicts = {receipt_key(left) for left in matched['forecasts'] for right in matched['comparisons']
                     if receipt_key(left) == receipt_key(right) and not same_forecast(left, right)}
        if conflicts:
            row_invalid = invalid = True
            matched = {kind: [r for r in receipts if receipt_key(r) not in conflicts]
                       for kind, receipts in matched.items()}
        series['forecasts'] = matched['forecasts']
        if matched['comparisons']:
            series['comparisons'] = legacy + matched['comparisons']
        coverage = {key: len(value) for key, value in zip(('forecastCount', 'comparisonCount'), matched.values())}
        totals = {key: totals[key] + coverage[key] for key in totals}
        series['forecastCoverage'] = {'status': cache['status'] if not row_invalid else 'partial',
                                      'provider': cache['provider'], 'checkedAt': cache.get('checkedAt'), **coverage}
    inflation['forecastCoverage'] = {'status': 'partial' if enabled and invalid else cache['status'],
                                    'provider': cache['provider'], 'checkedAt': cache.get('checkedAt'), **totals}


def build_te_cache(raw: bytes, *, event_mapping: dict, archive_url: str, retrieved_at: str,
                   rights_confirmed: bool = False, now: datetime | None = None,
                   max_bytes: int = MAX_BYTES, max_rows: int = MAX_ROWS) -> dict:
    """Adapt licensed calendar bytes; no vendor Actual/vintage claims are made.

    ReferenceDate must contain an explicit ISO reference month/date. Calendar
    event IDs and rate/basis mappings must be verified by the operator. The
    supplied retrieval timestamp is the real acquisition time, never backdated.
    """
    if rights_confirmed is not True:
        return empty_cache()
    if not isinstance(raw, bytes) or len(raw) > min(max_bytes, MAX_BYTES):
        raise ValueError('provider byte bound exceeded')
    rows = decode_json(raw)
    if not isinstance(rows, list) or len(rows) > min(max_rows, MAX_ROWS):
        raise ValueError('provider row bound exceeded')
    current = now or datetime.now(timezone.utc)
    archive = {'url': archive_url, 'eventId': 'validation', 'contentSha256': hashlib.sha256(raw).hexdigest()}
    if not archive_valid({'retrievedAt': retrieved_at, 'archive': archive}, current):
        raise ValueError('safe archive URL and actual retrieval time required')
    result = empty_cache('ok')
    result['checkedAt'] = retrieved_at
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            result['status'] = 'partial'
            continue
        if row.get('CalendarID') is not None and row.get('CalendarId') is not None and str(row['CalendarID']) != str(row['CalendarId']):
            result['status'] = 'partial'
            continue
        event = row.get('CalendarID') or row.get('CalendarId')
        if isinstance(event, int) and not isinstance(event, bool):
            event = str(event)
        mapping = event_mapping.get(event) if isinstance(event, str) else None
        if not isinstance(mapping, dict):
            result['status'] = 'partial'
            continue
        reference = row.get('ReferenceDate')
        month = None
        if isinstance(reference, str):
            if re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', reference):
                month = reference
            else:
                try:
                    if re.match(r'^\d{4}-\d{2}-\d{2}(T|$)', reference):
                        month = datetime.fromisoformat(reference.replace('Z', '+00:00')).strftime('%Y-%m')
                except ValueError:
                    pass
        value = row.get('ForecastValue')
        if value is None:
            value = row.get('Forecast')
        if isinstance(value, str) and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*%?', value.strip()):
            value = float(value.strip().rstrip('%').strip())
        receipt = {key: mapping.get(key) for key in ('seriesId', 'rate', 'basis')}
        receipt.update(month=month, unit='%', expected=value, evidenceKind='provider_archive', retrievedAt=retrieved_at,
                       archive={**archive, 'eventId': event}, source={'forecastName': PROVIDER,
                       'forecastUrl': archive_url})
        if row.get('Unit') != '%' or not forecast_valid(receipt, current) or month > current.strftime('%Y-%m'):
            result['status'] = 'partial'
            continue
        key = receipt_key(receipt)
        if key in seen:
            raise ValueError('duplicate provider forecast identity')
        seen.add(key)
        result['forecasts'].append(receipt)
    return result


def fetch_te_cache(transport: Callable[[], bytes], *, rights_confirmed: bool = False, **options: Any) -> dict:
    """Explicit injected acquisition only; this module provides no HTTP client.

    Transport owners must bound download size/time. Byte/row limits are checked
    again by build_te_cache. App readers never invoke this helper.
    """
    if rights_confirmed is not True:
        return empty_cache()
    return build_te_cache(transport(), rights_confirmed=True, **options)


def main() -> None:
    """Offline import only; no credential handling or provider calls."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=CACHE_PATH)
    parser.add_argument('--archive-url', required=True)
    parser.add_argument('--retrieved-at', required=True)
    parser.add_argument('--rights-confirmed', action='store_true', help='Operator has verified public display and historical retention rights')
    args = parser.parse_args()
    result = empty_cache()
    if args.rights_confirmed:
        with args.input.open('rb') as handle:
            raw = handle.read(MAX_BYTES + 1)
        with args.mapping.open('rb') as handle:
            mapping_raw = handle.read(MAX_BYTES + 1)
        if len(mapping_raw) > MAX_BYTES:
            parser.error('mapping byte bound exceeded')
        result = build_te_cache(raw, event_mapping=decode_json(mapping_raw), archive_url=args.archive_url,
                                retrieved_at=args.retrieved_at, rights_confirmed=True)
    # Complete validation precedes replacement; bad import preserves old cache.
    temporary = args.output.with_name(args.output.name + '.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(args.output)


if __name__ == '__main__':
    main()
