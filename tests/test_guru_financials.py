import copy
import pytest
from guru_financials import normalize_reports


def report(year=2025, receipt='20260312001224'):
    accounts = [('BS', 'ifrs-full_Equity', '자본총계', '100'),
                ('BS', 'ifrs-full_Liabilities', '부채총계', '80'),
                ('BS', 'ifrs-full_Assets', '자산총계', '180'),
                ('IS', 'ifrs-full_ProfitLoss', '당기순이익', '15'),
                ('CF', 'ifrs-full_CashFlowsFromUsedInOperatingActivities', '영업활동현금흐름', '20'),
                ('IS', 'ifrs-full_BasicEarningsLossPerShare', '기본주당이익', '1,234.50')]
    return {'year': year, 'basis': 'CFS', 'periodEnd': f'{year}-12-31',
            'periods':{p:{'start':f'{year-i}-01-01','end':f'{year-i}-12-31'} for i,p in enumerate(('thstrm','frmtrm','bfefrmtrm'))},
            'receiptNo': receipt, 'filingDate': f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}',
            'rows': [dict(sj_div=sj, account_id=aid, account_nm=name, currency='KRW',
                          rcept_no=receipt, account_detail='-', thstrm_amount=value,
                          frmtrm_amount=value, bfefrmtrm_amount=value)
                     for sj, aid, name, value in accounts]}


def normalized(reports=None, actions=None):
    return normalize_reports(reports or [report(2023, '20240312001224'), report()],
                             symbol='005930.KS', classification={'status': 'supported', 'source': 'KIND', 'industry': '전자부품 제조업'},
                             actions=actions or {'status': 'verified', 'source': 'verified-action-history',
                                                'start': '2021-01-01', 'end': '2026-10-02', 'events': []})


def test_four_annual_years_and_latest_restated_values():
    old, new = report(2023, '20240312001224'), report()
    new['rows'][3]['frmtrm_amount'] = '19'
    result = normalized([old, new])
    assert [r['year'] for r in result['annual']] == [2022, 2023, 2024, 2025]
    assert result['annual'][2]['netIncome'] == 19
    assert result['sources']['2024']['netIncome']['receiptNo'] == '20260312001224'


def test_eps_decimal_and_common_basic_selection():
    assert normalized()['annual'][-1]['basicEps'] == 1234.5
    data = report()
    data['rows'][-1]['account_id'] = 'ifrs-full_DilutedEarningsLossPerShare'
    data['rows'][-1]['account_nm'] = '희석주당이익'
    assert normalized([data])['annual'][-1]['basicEps'] is None
    data = report()
    data['rows'][-1]['account_nm'] = '우선주기본주당이익'
    assert normalized([data])['annual'][-1]['basicEps'] is None


@pytest.mark.parametrize('change', ['basis', 'currency', 'period'])
def test_basis_currency_period_mismatch(change):
    old, new = report(2023, '20240312001224'), report()
    if change == 'basis': old['basis'] = 'OFS'
    if change == 'currency': old['rows'][0]['currency'] = 'USD'
    if change == 'period': old['periodEnd'] = '2023-06-30'
    result = normalized([old, new])
    assert len(result['annual']) < 4 or result['annual'][0]['equity'] is None


def test_duplicate_accounts_not_summed():
    data = report()
    data['rows'].append(copy.deepcopy(data['rows'][0]))
    assert normalized([data])['annual'][-1]['equity'] is None
    data = report()
    data['rows'].append(copy.deepcopy(data['rows'][-1]))
    assert normalized([data])['annual'][-1]['basicEps'] is None


def test_unknown_actions_not_no_actions():
    result = normalized(actions={'status': 'error', 'events': []})
    assert result['epsComparability']['status'] == 'unknown'

def test_short_or_unverified_income_period_is_not_annual():
    old,new=report(2023,'20240312001224'),report()
    new['periods']['thstrm']['start']='2025-07-01'
    assert normalized([old,new])['annualReportYear']!=2025
    new=report();new.pop('periods')
    assert normalized([new])['annual']==[]

def test_short_comparative_period_cannot_supply_eps_or_cash():
    new=report();new['periods']['frmtrm']['start']='2024-07-01'
    data=normalized([new])
    assert data['annual'][-2]['basicEps'] is None
    assert data['annual'][-2]['operatingCashFlow'] is None

@pytest.mark.parametrize('row',[
 {'symbol':'330590.KS','name':'롯데리츠','industry':'부동산 임대 및 공급업','mainProducts':'부동산투자'},
 {'symbol':'088260.KS','name':'이리츠코크렙','industry':'부동산 임대 및 공급업','mainProducts':'부동산투자회사'},
 {'symbol':'293940.KS','name':'신한알파리츠','industry':'부동산 임대 및 공급업','mainProducts':'비거주 부동산 임대 서비스업'},
])
def test_real_estate_type_is_not_assumed_ordinary(row):
    from guru_financials import classify_company
    assert classify_company(row)['status'] in {'unsupported','unknown'}


def test_split_without_verified_restatement_is_not_comparable():
    result = normalized(actions={'status': 'verified', 'source': 'test', 'start': '2021-01-01',
                                 'end': '2026-10-02', 'events': [{'date': '2024-01-03', 'ratio': 2}]})
    assert result['epsComparability']['status'] == 'unknown'


def test_negative_and_non_finite_numbers_preserve_missing():
    data = report()
    data['rows'][3]['thstrm_amount'] = '(1,234)'
    data['rows'][0]['thstrm_amount'] = 'NaN'
    result = normalized([data])
    assert result['annual'][-1]['netIncome'] == -1234
    assert result['annual'][-1]['equity'] is None


@pytest.mark.parametrize('account_id', ['ifrs-full_BasicEarningsLossPerShare', 'ifrs_BasicEarningsLossPerShare'])
def test_explicit_combined_label_preserves_official_basic_eps_account(account_id):
    data = report()
    data['rows'][-1].update(account_id=account_id, account_nm='보통주 기본 및 희석주당순이익', thstrm_amount='2,916')
    result = normalized([data])
    assert result['annual'][-1]['basicEps'] == 2916
    assert result['sources']['2025']['basicEps']['accountId'] == account_id
    assert result['sources']['2025']['basicEps']['accountName'] == '보통주 기본 및 희석주당순이익'


@pytest.mark.parametrize('account_id,label', [
    ('ifrs-full_BasicEarningsLossPerShare', '희석주당이익'),
    ('ifrs-full_BasicEarningsLossPerShare', '우선주 기본 및 희석주당이익'),
    ('ifrs-full_DilutedEarningsLossPerShare', '기본주당이익'),
    ('ifrs-full_DilutedEarningsLossPerShare', '기본 및 희석주당이익'),
    ('custom_CombinedEps', '기본 및 희석주당이익'),
])
def test_combined_label_does_not_accept_diluted_preferred_or_unverified_custom_eps(account_id, label):
    data = report()
    data['rows'][-1].update(account_id=account_id, account_nm=label)
    assert normalized([data])['annual'][-1]['basicEps'] is None


def test_combined_basic_eps_remains_ambiguous_with_duplicate_accounts():
    data = report()
    data['rows'][-1]['account_nm'] = '기본 및 희석주당이익'
    data['rows'].append(copy.deepcopy(data['rows'][-1]))
    assert normalized([data])['annual'][-1]['basicEps'] is None
