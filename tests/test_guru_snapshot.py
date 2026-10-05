import copy
import json
import pytest
from guru_snapshot import build_snapshot, publish_snapshot
from test_guru_rules import company, quote


def inputs():
    c, q = company(), quote()
    return [{'symbol': '005930.KS', 'name': '테스트 기업', 'market': 'KOSPI', 'industry': '전자부품 제조업'}], {'tradeDate': q['date'], 'stocks': [q]}, {'companies': {'005930.KS': c}}


def test_counts_partition_universe():
    universe, prices, financials = inputs()
    for i, status in enumerate(['unsupported', 'pending', 'insufficient', 'failed', 'failed'], 1):
        symbol = f'{i:06}.KS'
        universe.append({'symbol': symbol, 'name': f'시험 {i}', 'market': 'KOSPI', 'industry': '일반 제조업'})
        c = copy.deepcopy(company()); c['symbol'] = symbol
        q = dict(quote(), symbol=symbol); prices['stocks'].append(q)
        if status=='unsupported': universe[-1]['industry']='은행 및 금융업'
        if status=='pending': c['collection']['status'] = 'pending'
        if status=='insufficient': c['annual'][0]['equity'] = None
        if status=='failed': c['annual'][-1]['netIncome'] = 0
        financials['companies'][symbol] = c
    data, evidence = build_snapshot(universe, prices, financials, generated_at='2026-10-05T17:00:00+09:00')
    s=data['strategies']['buffett']
    assert [s[k] for k in ['universeCount','unsupportedCount','pendingCount','insufficientCount','failedCount','matchedCount','evaluatedCount']] == [6,1,1,1,2,1,3]
    assert evidence['snapshotVersion'] == data['snapshotVersion']


def test_removed_or_changed_symbol_never_resurrects():
    u,p,f=inputs()
    data,evidence=build_snapshot([],p,f,generated_at='2026-10-05T17:00:00+09:00')
    assert data['strategies']['buffett']['results']==[]
    assert evidence['companies']=={}


def test_missing_current_quote_not_carried_as_current():
    u,p,f=inputs(); p['stocks'][0]['date']='2026-10-01'
    data,_=build_snapshot(u,p,f,generated_at='2026-10-05T17:00:00+09:00')
    assert data['strategies']['buffett']['insufficientCount']==1


def test_invalid_publish_preserves_last_good_files(tmp_path):
    data,evidence=build_snapshot(*inputs(),generated_at='2026-10-05T17:00:00+09:00')
    publish_snapshot(data,evidence,tmp_path)
    original=(tmp_path/'guru_screening.json').read_bytes()
    data['strategies']['buffett']['universeCount']=100
    with pytest.raises(ValueError): publish_snapshot(data,evidence,tmp_path)
    assert (tmp_path/'guru_screening.json').read_bytes()==original


def test_corrected_report_invalidates_dependent_metrics():
    u,p,f=inputs()
    before,_=build_snapshot(u,p,f,generated_at='2026-10-05T17:00:00+09:00')
    f['companies']['005930.KS']['annual'][-1]['netIncome']=1
    after,_=build_snapshot(u,p,f,generated_at='2026-10-05T17:00:00+09:00')
    assert before['snapshotVersion'] != after['snapshotVersion']
    assert after['strategies']['buffett']['matchedCount']==0

def test_current_industry_takes_precedence_over_cached_classification():
    u,p,f=inputs(); u[0]['industry']='은행 및 금융업'
    data,_=build_snapshot(u,p,f,generated_at='2026-10-05T17:00:00+09:00')
    assert data['strategies']['buffett']['unsupportedCount']==1

def test_snapshot_financial_check_time_is_not_refresh_attempt_time():
    u,p,f=inputs(); f['generatedAt']='2026-10-05T17:00:00+09:00'
    f['companies']['005930.KS']['checkedAt']='2026-10-01T17:00:00+09:00'
    data,_=build_snapshot(u,p,f,generated_at=f['generatedAt'])
    assert data['financialAsOf']=='2026-10-01T17:00:00+09:00'
