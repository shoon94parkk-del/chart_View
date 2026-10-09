"""Provider-free integration: retained DART amounts -> metrics -> API evidence."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from guru_financials import KEYS, amount
import guru_service

DATA = Path(__file__).resolve().parents[1] / 'static/data'


@pytest.fixture(scope='module')
def saved():
    return {name: json.loads((DATA / f'guru_{name}.json').read_text(encoding='utf-8'))
            for name in ('financials', 'screening', 'evidence')}


def test_saved_financial_evidence_has_actual_same_basis_receipt_amounts(saved):
    evidence, financials = saved['evidence'], saved['financials']
    assert evidence['snapshotVersion'] == saved['screening']['snapshotVersion']
    assert evidence['tradeDate'] == saved['screening']['tradeDate']
    for symbol, company in evidence['companies'].items():
        original = financials['companies'][symbol]
        assert company['annual'] == original['annual']
        assert company['sources'] == original['sources']
        for annual in company['annual']:
            year = annual['year']
            for key in KEYS:
                value = annual.get(key)
                if value is None:
                    continue
                source = company['sources'][str(year)][key]
                assert source['currency'] == 'KRW'
                assert source['periodStart'] == f'{year}-01-01'
                assert source['periodEnd'] == f'{year}-12-31'
                reports = [r for r in original['reports']
                           if r['receiptNo'] == source['receiptNo'] and r['basis'] == company['basis']]
                assert len(reports) == 1, (symbol, year, key)
                assert reports[0]['periods'][source['period'].removesuffix('_amount')] == {
                    'start': source['periodStart'], 'end': source['periodEnd']}
                statements = {'IS', 'CIS'} if key in {'netIncome', 'basicEps'} else {'CF'} if key == 'operatingCashFlow' else {'BS'}
                accounts = [r for r in reports[0]['rows']
                            if r.get('account_id') == source['accountId']
                            and r.get('account_nm') == source['accountName']
                            and r.get('sj_div') in statements
                            and str(r.get('account_detail') or '-').strip() in {'', '-'}
                            and r.get('rcept_no') == source['receiptNo'] and r.get('currency') == 'KRW']
                assert any(amount(r.get(source['period'])) == value for r in accounts), (symbol, year, key)


@pytest.mark.parametrize('strategy', ['buffett', 'lynch', 'greenblatt'])
def test_saved_selected_metrics_follow_original_annual_arithmetic(saved, strategy):
    for row in saved['screening']['strategies'][strategy]['results']:
        annual = sorted(saved['evidence']['companies'][row['symbol']]['annual'], key=lambda r: r['year'])
        metrics, latest = row['metrics'], annual[-1]
        if strategy in {'buffett', 'lynch'}:
            assert metrics['debtRatio'] == pytest.approx(latest['liabilities'] / latest['equity'] * 100)
        if strategy == 'buffett':
            years = annual[-4:]
            roe = [years[i]['netIncome'] / ((years[i-1]['equity'] + years[i]['equity']) / 2) * 100
                   for i in range(1, 4)]
            assert metrics['roeAvg3'] == pytest.approx(sum(roe) / 3)
            assert metrics['roeMin3'] == pytest.approx(min(roe))
            assert metrics['cashConversion3'] == pytest.approx(
                sum(r['operatingCashFlow'] for r in years[1:]) / sum(r['netIncome'] for r in years[1:]) * 100)
        elif strategy == 'lynch':
            growth = ((latest['basicEps'] / annual[-4]['basicEps']) ** (1/3) - 1) * 100
            assert metrics['basicEps'] == latest['basicEps']
            assert metrics['epsCagr3'] == pytest.approx(growth)
            assert metrics['historicalPEG'] == pytest.approx(metrics['annualPE'] / growth)
        else:
            assert metrics['annualROA'] == pytest.approx(latest['netIncome'] / latest['assets'] * 100)


def test_cache_only_api_returns_same_version_values_and_rejects_obsolete_version(saved, monkeypatch):
    monkeypatch.setattr(guru_service, 'EVIDENCE_PATH', DATA / 'guru_evidence.json')
    monkeypatch.setattr(guru_service, '_cache_key', None)
    monkeypatch.setattr(guru_service, '_cache', {})
    app = FastAPI()
    app.include_router(guru_service.router)
    with TestClient(app) as client:
        version = saved['screening']['snapshotVersion']
        for strategy in saved['screening']['strategies'].values():
            if not strategy['results']:
                continue
            symbol = strategy['results'][0]['symbol']
            response = client.get(f'/api/guru-investing/{symbol}', params={'version': version})
            assert response.status_code == 200
            actual = response.json()
            original = saved['evidence']['companies'][symbol]
            assert actual['snapshotVersion'] == version
            assert actual['annual'] == original['annual']
            assert actual['sources'] == original['sources']
            assert actual['strategies'] == original['strategies']
        response = client.get('/api/guru-investing/005930.KS', params={'version': 'obsolete-source-proof'})
        assert response.status_code == 409
        assert response.json()['detail']['currentVersion'] == version
