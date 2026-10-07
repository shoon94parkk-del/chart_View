"""Comparable annual evidence for guru-reference screens, never synthetic EPS."""
from __future__ import annotations

from datetime import date
import math
import re

from dart_financial_service import QUALITY_ACCOUNTS, _pick_account

KEYS = ('netIncome', 'operatingCashFlow', 'assets', 'liabilities', 'equity', 'basicEps')


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).replace(',', '').replace(' ', '').strip()
    if text.startswith('△'):
        text = '-' + text[1:]
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    try:
        result = float(text)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def classify_company(row):
    industry = str(row.get('industry') or '').strip()
    security = row.get('securityType')
    if security in {'preferred', 'reit', 'spac', 'etf', 'etn'}:
        status = 'unsupported'
    elif re.search(r'금융|은행|보험|신탁|집합투자|증권|기업인수목적', industry):
        status = 'unsupported'
    elif re.search(r'부동산투자회사|리츠',str(row.get('mainProducts') or '')):
        status = 'unsupported'
    elif '부동산' in industry and security != 'common':
        status = 'unknown'
    elif industry and re.fullmatch(r'\d{6}\.(KS|KQ)', row.get('symbol', '')):
        status = 'supported'
    else:
        status = 'unknown'
    return {'status': status, 'industry': industry, 'source': 'KIND listing industry/security type'}


def _eps_account(rows):
    basic_ids = {'ifrs-full_BasicEarningsLossPerShare', 'ifrs_BasicEarningsLossPerShare'}
    diluted_ids = {'ifrs-full_DilutedEarningsLossPerShare', 'ifrs_DilutedEarningsLossPerShare'}
    eligible = [r for r in rows if r.get('sj_div') in {'IS', 'CIS'}
                and str(r.get('account_detail') or '-').strip() in {'', '-'}
                and '우선' not in r.get('account_nm', '')
                and r.get('account_id') not in diluted_ids
                and ('희석' not in r.get('account_nm', '') or
                     r.get('account_id') in basic_ids and
                     re.search(r'기본(?:및|과|/|·|ㆍ)희석', r.get('account_nm', '').replace(' ', '')))
                and (r.get('account_id') in basic_ids
                     or re.fullmatch(r'(보통주)?기본주당(이익|손익|순이익)(\(손실\))?', r.get('account_nm', '').replace(' ', '')))]
    ordinary = [r for r in eligible if '보통' in r.get('account_nm', '')]
    eligible = ordinary or eligible
    for sj in ('IS', 'CIS'):
        part = [r for r in eligible if r.get('sj_div') == sj]
        if part:
            return part[0] if len(part) == 1 else None
    return None


def normalize_reports(reports: list[dict], *, symbol: str, classification: dict, actions: dict) -> dict:
    valid = [r for r in reports if r.get('basis') in {'CFS', 'OFS'}
             and isinstance(r.get('year'), int) and re.fullmatch(r'\d{14}', r.get('receiptNo', ''))
             and r.get('periodEnd') == f"{r['year']}-12-31"
             and (r.get('periods') or {}).get('thstrm') == {'start':f"{r['year']}-01-01",'end':f"{r['year']}-12-31"}]
    basis = 'CFS' if any(r['basis'] == 'CFS' for r in valid) else 'OFS'
    valid = [r for r in valid if r['basis'] == basis]
    values, sources = {}, {}
    for report in sorted(valid, key=lambda r: r['receiptNo']):
        rows = report.get('rows') or []
        for key in KEYS:
            if key == 'basicEps':
                account = _eps_account(rows)
            else:
                names, ids, statements = QUALITY_ACCOUNTS[key]
                account = _pick_account(rows, names, ids, statements)
            if account and (account.get('currency') != 'KRW' or account.get('rcept_no') != report['receiptNo']):
                account = None
            for offset, period in enumerate(('thstrm_amount', 'frmtrm_amount', 'bfefrmtrm_amount')):
                year = report['year'] - offset
                observed = (report.get('periods') or {}).get(period.removesuffix('_amount'))
                annual_period = observed == {'start':f'{year}-01-01','end':f'{year}-12-31'}
                values.setdefault(year, {'year': year, **dict.fromkeys(KEYS)})
                # A newer ambiguous account invalidates its older observations.
                values[year][key] = amount(account.get(period)) if account and annual_period else None
                sources.setdefault(str(year), {})[key] = {
                    'receiptNo': report['receiptNo'], 'filingDate': report['filingDate'],
                    'accountId': account.get('account_id') if account else None,
                    'accountName': account.get('account_nm') if account else None,
                    'currency': 'KRW', 'period': period, 'reportYear': report['year'],
                    'periodStart': (observed or {}).get('start'), 'periodEnd': (observed or {}).get('end'),
                    'sourceUrl': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={report['receiptNo']}",
                }
    latest = max(values, default=0)
    annual = [values[y] for y in sorted(values) if latest - 3 <= y <= latest]
    comparable = (actions.get('status') == 'verified' and bool(actions.get('source'))
                  and bool(annual) and str(actions.get('start', '')) <= f'{latest-3}-01-01'
                  and str(actions.get('end', '')) >= f'{latest+1}-01-01' and not actions.get('events'))
    return {'symbol': symbol, 'stockCode': symbol.split('.')[0], 'classification': classification,
            'basis': basis, 'currency': 'KRW', 'annualReportYear': latest, 'annual': annual, 'sources': sources,
            'epsComparability': {'status': 'verified' if comparable else 'unknown',
                                 'reason': None if comparable else '주당 기준·기업행동 확인 부족',
                                 'source': actions.get('source'), 'start': actions.get('start'),
                                 'end': actions.get('end'), 'events': actions.get('events', [])}}
