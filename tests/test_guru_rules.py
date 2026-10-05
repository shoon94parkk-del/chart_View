import copy
import math
import pytest
from guru_rules import evaluate_company


def company():
    return {'symbol': '005930.KS', 'currency': 'KRW', 'basis': 'CFS', 'annualReportYear': 2025,
            'classification': {'status': 'supported'}, 'collection': {'status': 'complete'},
            'epsComparability': {'status': 'verified', 'end': '2026-10-02'},
            'sources': {'2025': {'equity': {'filingDate': '2026-03-12'}}},
            'annual': [{'year': 2022+i, 'equity': 100, 'liabilities': 100,
                        'netIncome': [8, 10, 15, 20][i], 'operatingCashFlow': [8, 10, 15, 20][i],
                        'basicEps': [100, 120, 144, 172.8][i]} for i in range(4)]}


def quote():
    return {'symbol': '005930.KS', 'price': 3456, 'date': '2026-10-02', 'currency': 'KRW'}


def test_buffett_boundaries():
    result = evaluate_company(company(), quote(), strategy='buffett')
    assert result['status'] == 'matched'
    assert result['metrics']['roeAvg3'] == 15
    assert result['metrics']['debtRatio'] == 100
    c = company()
    c['annual'][-1]['operatingCashFlow'] = 19
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'failed'


def test_lynch_percent_units_and_annual_pe():
    result = evaluate_company(company(), quote(), strategy='lynch')
    assert result['status'] == 'matched'
    assert result['metrics']['epsCagr3'] == pytest.approx(20)
    assert result['metrics']['annualPE'] == pytest.approx(20)
    assert result['metrics']['historicalPEG'] == pytest.approx(1)


@pytest.mark.parametrize('rate', [10, 30])
def test_lynch_growth_endpoints(rate):
    c, q = company(), quote()
    for i, row in enumerate(c['annual']): row['basicEps'] = 100*(1+rate/100)**i
    q['price'] = c['annual'][-1]['basicEps']*rate
    assert evaluate_company(c, q, strategy='lynch')['status'] == 'matched'


@pytest.mark.parametrize('value', [None, float('nan'), float('inf')])
def test_missing_and_nonfinite_never_pass(value):
    c = company()
    c['annual'][-1]['equity'] = value
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'insufficient'


def test_zero_negative_and_recent_eps_decline_fail():
    c = company()
    c['annual'][-1]['netIncome'] = 0
    assert evaluate_company(c, quote(), strategy='buffett')['status'] != 'matched'
    c = company()
    c['annual'][-2]['basicEps'] = 200
    assert evaluate_company(c, quote(), strategy='lynch')['status'] == 'failed'
    c = company()
    c['annual'][0]['basicEps'] = -1
    assert evaluate_company(c, quote(), strategy='lynch')['status'] == 'failed'


def test_three_years_basis_and_action_uncertainty_are_insufficient():
    c = company(); c['annual'] = c['annual'][1:]
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'insufficient'
    c = company(); c['epsComparability']['status'] = 'unknown'
    assert evaluate_company(c, quote(), strategy='lynch')['status'] == 'insufficient'


def test_unmatched_quote_and_future_filing_are_rejected():
    q = quote(); q['symbol'] = '000660.KS'
    assert evaluate_company(company(), q, strategy='lynch')['status'] == 'insufficient'
    c = company(); c['sources']['2025']['equity']['filingDate'] = '2026-10-03'
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'insufficient'


def test_pending_unsupported_and_unknown_classification_are_distinct():
    c = company(); c['classification']['status'] = 'unsupported'
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'unsupported'
    c = company(); c['classification']['status'] = 'unknown'
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'insufficient'
    c = company(); c['collection']['status'] = 'pending'
    assert evaluate_company(c, quote(), strategy='buffett')['status'] == 'pending'

def test_prior_annual_is_valid_before_annual_filing_deadline():
    q=quote(); q['date']='2026-02-20'
    c=company(); c['annualReportYear']=2024
    for r in c['annual']: r['year']-=1
    c['sources']={'2024':{'equity':{'filingDate':'2025-03-12'}}}
    assert evaluate_company(c,q,strategy='buffett')['status']=='matched'
    q['date']='2026-04-01'
    assert evaluate_company(c,q,strategy='buffett')['status']=='insufficient'

def test_lynch_needs_latest_cash_and_debt_not_four_years_of_them():
    c=company()
    for r in c['annual'][:-1]:
        r.pop('operatingCashFlow'); r.pop('liabilities'); r.pop('equity')
    assert evaluate_company(c,quote(),strategy='lynch')['status']=='matched'

def test_failed_refresh_never_publishes_old_company_as_current_verified():
    c=company();c['refreshError']='DART network error'
    assert evaluate_company(c,quote(),strategy='lynch')['status']=='insufficient'
