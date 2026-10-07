"""Bounded incremental official-disclosure review; never synthetic EPS or dates."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import re

from guru_financials import normalize_reports

_ACTION = re.compile(r'주식배당|주식분할|주식병합|무상증자|주식분할.*병합')
_FINANCIAL = re.compile(r'사업보고서|반기보고서|분기보고서')


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid_date')
    return date.fromisoformat(value)


def _integer(value):
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise ValueError('invalid_pagination')
    return int(value)


def renormalize_cached_reports(cache):
    """Re-read retained official basic-EPS rows, preserving financial verification."""
    result = deepcopy(cache)
    companies = result.get('companies') or {}
    changed_companies = changed_observations = 0
    for symbol, company in companies.items():
        reports = company.get('reports')
        if not isinstance(reports, list) or not reports or company.get('symbol') != symbol:
            continue
        normalized = normalize_reports(reports, symbol=symbol,
                                       classification=company.get('classification') or {},
                                       actions=company.get('actions') or {})
        old_rows = company.get('annual') or []
        new_rows = normalized.get('annual') or []
        if (company.get('basis') != normalized.get('basis') or
                company.get('annualReportYear') != normalized.get('annualReportYear') or
                [r.get('year') for r in old_rows] != [r.get('year') for r in new_rows]):
            continue
        changed = False
        for old, new in zip(old_rows, new_rows):
            year = str(old['year'])
            old_source = (company.get('sources') or {}).get(year, {}).get('basicEps')
            new_source = (normalized.get('sources') or {}).get(year, {}).get('basicEps')
            if old.get('basicEps') == new.get('basicEps') and old_source == new_source:
                continue
            old['basicEps'] = new.get('basicEps')
            company.setdefault('sources', {}).setdefault(year, {})['basicEps'] = deepcopy(new_source)
            changed_observations += 1
            changed = True
        changed_companies += int(changed)
    result['epsNormalization'] = {'updatedCompanies': changed_companies,
                                  'updatedObservations': changed_observations}
    return result


def refresh_action_windows(cache, *, client, trade_date, checked_at, max_pages=100):
    """Atomically review a <=31-day missing window using the existing DART budget.

    client.get enforces the collector's shared request/deadline/020 limits. Only
    complete, identity-bound pagination can advance a previously verified scope.
    Financial values, source receipts and financial checkedAt are never changed.
    """
    original = deepcopy(cache)
    requests_before = getattr(client, 'requests', 0)
    metadata = {'status': 'unavailable', 'eligibleCount': 0, 'updatedCount': 0,
                'blockedCount': 0, 'requests': 0, 'start': None, 'end': trade_date,
                'checkedAt': checked_at, 'reason': None}

    def finish(value, status, reason=None):
        metadata.update(status=status, reason=reason,
                        requests=max(0, getattr(client, 'requests', 0) - requests_before))
        value['actionCollection'] = deepcopy(metadata)
        return value

    try:
        end = _day(trade_date)
        checked = datetime.fromisoformat(checked_at)
        if checked.tzinfo is None or end > checked.date() or not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 100:
            raise ValueError('invalid_review_bounds')
        universe = {row.get('symbol') for row in original.get('universe', [])}
        targets = {}
        corp_codes = getattr(client, 'corp_codes', {})
        for symbol, company in (original.get('companies') or {}).items():
            actions = company.get('actions') or {}
            eps = company.get('epsComparability') or {}
            if (symbol not in universe or company.get('symbol') != symbol or
                    not re.fullmatch(r'\d{6}\.(KS|KQ)', symbol) or
                    (company.get('classification') or {}).get('status') != 'supported' or
                    eps.get('status') != 'verified' or actions.get('status') != 'verified' or
                    actions.get('events') or eps.get('events') or
                    eps.get('source') != actions.get('source') or
                    not str(actions.get('source', '')).startswith('OpenDART disclosures') or
                    eps.get('start') != actions.get('start') or eps.get('end') != actions.get('end')):
                continue
            try:
                start, old_end = _day(actions.get('start')), _day(actions.get('end'))
            except (TypeError, ValueError):
                continue
            corp = company.get('corpCode')
            mapped = (corp_codes.get(symbol.split('.')[0]) or {}).get('corpCode')
            if (not re.fullmatch(r'\d{8}', str(corp or '')) or corp != mapped or
                    start > old_end or old_end >= end):
                continue
            targets[symbol] = {'corp': corp, 'oldEnd': old_end}
        metadata['eligibleCount'] = len(targets)
        if not targets:
            return finish(original, 'complete')
        window_start = min(t['oldEnd'] for t in targets.values()) + timedelta(days=1)
        metadata['start'] = window_start.isoformat()
        if (end - window_start).days >= 31:
            return finish(original, 'unavailable', 'review_window_exceeds_31_days')
        filings, seen, expected = [], set(), None
        for page in range(1, max_pages + 1):
            packet = client.get('list.json', {'bgn_de': window_start.strftime('%Y%m%d'),
                'end_de': end.strftime('%Y%m%d'), 'page_count': 100, 'page_no': page,
                'sort': 'date', 'sort_mth': 'asc'})
            if packet.get('status') == '013':
                if page != 1 or packet.get('list'):
                    raise ValueError('incomplete_pagination')
                break
            if packet.get('status') != '000':
                raise ValueError('provider_status_not_success')
            total, pages = _integer(packet.get('total_count')), _integer(packet.get('total_page'))
            current, size = _integer(packet.get('page_no')), _integer(packet.get('page_count'))
            rows = packet.get('list')
            if (current != page or size != 100 or pages != (total + 99) // 100 or
                    not isinstance(rows, list) or len(rows) != max(0, min(100, total - (page - 1) * 100)) or
                    expected is not None and expected != (total, pages)):
                raise ValueError('invalid_pagination')
            expected = total, pages
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('invalid_filing')
                corp, receipt, observed, name = [row.get(k) for k in ('corp_code', 'rcept_no', 'rcept_dt', 'report_nm')]
                if (not re.fullmatch(r'\d{8}', str(corp or '')) or not re.fullmatch(r'\d{14}', str(receipt or '')) or
                        not re.fullmatch(r'\d{8}', str(observed or '')) or receipt in seen or
                        not isinstance(name, str) or not name.strip()):
                    raise ValueError('invalid_filing_identity')
                day = _day(f'{observed[:4]}-{observed[4:6]}-{observed[6:]}')
                if not window_start <= day <= end or receipt[:8] != observed:
                    raise ValueError('invalid_filing_date')
                seen.add(receipt)
                filings.append((corp, day, name, receipt))
            if page >= pages:
                if len(filings) != total:
                    raise ValueError('incomplete_pagination')
                break
        else:
            raise ValueError('page_budget_incomplete')
        result = deepcopy(original)
        by_corp = {}
        for corp, day, name, receipt in filings:
            by_corp.setdefault(corp, []).append((day, name, receipt))
        for symbol, target in targets.items():
            company = result['companies'][symbol]
            actions, eps = company['actions'], company['epsComparability']
            events, financial_reports = [], []
            for day, name, receipt in by_corp.get(target['corp'], []):
                if day <= target['oldEnd']:
                    continue
                observed = {'date': day.strftime('%Y%m%d'), 'name': name, 'receiptNo': receipt}
                if _ACTION.search(name):
                    events.append(observed)
                if _FINANCIAL.search(name):
                    financial_reports.append(observed)
            actions['reviewBase'] = {'financialCheckedAt': company.get('checkedAt'),
                                    'previousEnd': actions['end'], 'corpCode': target['corp']}
            actions.update(end=trade_date, checkedAt=checked_at)
            eps['end'] = trade_date
            if events or financial_reports:
                actions['events'] = events
                if financial_reports:
                    actions['financialRefreshRequired'] = financial_reports
                eps.update(status='unknown', events=deepcopy(events),
                           reason='새 재무공시 재확인 필요' if financial_reports else '주당 기준·기업행동 확인 부족')
                metadata['blockedCount'] += 1
            metadata['updatedCount'] += 1
        return finish(result, 'complete')
    except Exception:
        # Never expose a provider exception containing its authenticated URL/key.
        return finish(original, 'unavailable', 'disclosure_review_not_completed')
