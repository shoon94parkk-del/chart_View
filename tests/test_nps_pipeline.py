"""Offline allocation, provenance, partial publication and corporate-action contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nps_pipeline', ROOT/'scripts/nps_pipeline.py')
nps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nps)


def config():
    return nps.load_json(ROOT/'scripts/nps/config.json')


def seed():
    return nps.load_json(ROOT/'docs/evidence/nps20261018/pipeline/seed-summary.json')


def test_published_exact_seed_model_matches_independent_python_recalculation():
    summary=seed()
    result=nps.calculate(summary['inputs'],summary['assetBaseline'])
    for key in ('weight','gap','adjustment','total','domestic','other','targetKospi','saaKospi','taaKospi','marketGain','fxGain'):
        assert result[key] == pytest.approx(summary['result'][key],rel=1e-12)
    assert summary['result']['weight'] == pytest.approx(22.776530917046365)
    assert summary['inputs']['equityReturn'] == pytest.approx(summary['filing']['blendedReturnPct'])


def test_seed_details_are_same_version_and_filing_usd_never_thousands():
    summary=seed();details=nps.load_json(ROOT/'static/data/nps'/summary['filing']['detailsFile'])
    assert summary['snapshotVersion']==details['snapshotVersion']
    assert summary['marketDate']==details['marketDate']=='2026-10-16'
    assert len(details['rows'])==552
    assert sum(r['reportValueUSD'] for r in details['rows'])==155079663358
    assert len([r for r in details['rows'] if r['method']=='direct'])==546
    f=summary['filing']
    assert f['base13fKRW']+f['residualBaseKRW']==pytest.approx(summary['baseline']['overseas'])
    assert f['blendedReturnPct']==pytest.approx((f['base13fKRW']*f['directReturnPct']+f['residualBaseKRW']*f['residualReturnPct'])/summary['baseline']['overseas'])
    assert all(r['totalReturnPct'] is None and r['currentValueUSD'] is None for r in details['rows'] if r['method']=='residual')


def charts(dates=('2026-07-31','2026-10-15','2026-10-16')):
    return {s:{'currency':c,'points':{d:{'close':100.,'adjustedClose':100.} for d in dates}} for s,c in nps.CORE.items()}


def test_common_session_uses_intersection_and_excludes_incomplete_cutoff():
    core=charts();del core['^KS11']['points']['2026-10-16']
    assert nps.common_session(core,'2026-10-16','2026-07-31')=='2026-10-15'
    core=charts()
    assert nps.common_session(core,'2026-10-15','2026-07-31')=='2026-10-15'


def test_common_session_rejects_stale_missing_baseline_and_wrong_currency():
    core=charts(('2026-07-31','2026-10-01'))
    with pytest.raises(ValueError,match='five calendar'):nps.common_session(core,'2026-10-16','2026-07-31')
    core=charts();del core['BNDW']['points']['2026-07-31']
    with pytest.raises(ValueError,match='baseline'):nps.common_session(core,'2026-10-16','2026-07-31')
    core=charts();core['KRW=X']['currency']='USD'
    with pytest.raises(ValueError,match='currency'):nps.common_session(core,'2026-10-16','2026-07-31')


def test_model_applies_cross_term_and_hedge_once_without_double_count():
    c=config();s={**c['inputs'],'hedgeRatio':0,'fxReturn':10,'otherReturn':0,
                  'equityReturn':20,'bondReturn':0,'domesticBondReturn':0,'alternativeReturn':0,'cashReturn':0}
    result=nps.calculate(s,c['assetBaseline'])
    equity=next(a for a in result['assets'] if a['id']=='equity')
    assert equity['projected']==pytest.approx(equity['base']*1.2*1.1)
    assert equity['fxGain']==pytest.approx(equity['base']*.12)
    s['hedgeRatio']=100
    assert nps.calculate(s,c['assetBaseline'])['fxGain']==0


def test_quality_gate_rejects_partial_or_newly_failed_priced_security():
    c={'filing':{'positionCount':2,'reportedValueUsd':100}}
    rows=[{'cusip':'A','ticker':'A','reportValueUSD':99.5,'valid':True},
          {'cusip':'B','ticker':'B','reportValueUSD':.5,'valid':False}]
    assert nps.quality_gate(rows,c)==pytest.approx(.995)
    with pytest.raises(ValueError,match='Previously priced'):
        nps.quality_gate(rows,c,{'rows':[{'cusip':'B','method':'direct'}]})
    rows[0]['valid']=False
    with pytest.raises(ValueError,match='coverage'):nps.quality_gate(rows,c)


def test_quality_gate_rejects_duplicate_cusip_and_report_total_mismatch():
    c={'filing':{'positionCount':2,'reportedValueUsd':100}}
    rows=[{'cusip':'A','ticker':'A','reportValueUSD':50,'valid':True}]*2
    with pytest.raises(ValueError,match='Duplicate'):nps.quality_gate(rows,c)
    c['filing']['reportedValueUsd']=100000
    with pytest.raises(ValueError,match='total mismatch'):nps.quality_gate(rows,c)


def test_publication_preserves_newer_and_evidence_version(tmp_path):
    s=seed();d=nps.load_json(ROOT/'static/data/nps'/s['filing']['detailsFile'])
    nps.publish(s,d,tmp_path)
    old=(tmp_path/'summary.json').read_bytes()
    older={**s,'marketDate':'2026-10-15'}
    with pytest.raises(ValueError,match='newer'):nps.publish(older,d,tmp_path)
    assert (tmp_path/'summary.json').read_bytes()==old
    wrong={**d,'snapshotVersion':'wrong'}
    with pytest.raises(ValueError,match='mismatch'):nps.publish(s,wrong,tmp_path)
    assert (tmp_path/'summary.json').read_bytes()==old


def test_frozen_share_split_basis_and_no_second_dividend_addition():
    q=nps.quotes
    h={'ticker':'TEST','cusip':'A','issuer':'Test','class':'COM','shares':10,'valueUsd':1000,'shareType':'SH'}
    dates=('2026-06-30','2026-07-31','2026-10-16')
    chart={'valid':True,'flags':[],'prices':{'report':{'close':50},'baseline':{'close':55},'current':{'close':60}},
           'events':{'splits':[{'date':'2026-08-01','numerator':2,'denominator':1}],'dividends':[{'date':'2026-09-01','amount':1}]},
           'totalReturn':.12}
    row=q.price_holding(h,chart,dates,.005)
    assert row['valid'] is True
    assert row['baselineMarketValueUSD']==1100
    assert row['currentMarketValueUSD']==1200
    assert row['currentTotalReturnValueUSD']==pytest.approx(1232)
    assert row['actualSharesAtBaseline']==10


def test_cash_merger_warrant_and_unverified_action_never_use_parent_quote():
    q=nps.quotes
    h={'ticker':'TEST','cusip':'A','issuer':'Test','class':'W EXP','shares':10,'valueUsd':1000}
    row=q.price_holding(h,None,('2026-06-30','2026-07-31','2026-10-16'),.005)
    assert not row['valid'] and row['flags']==['warrant_not_revalued_as_equity']
    actions=config()['corporateActions']
    assert actions['WBD']['decision']=='exclude'
    assert actions['SPGI']['decision']=='exclude'
    assert actions['SCCO']['verifiedFactor']==1.012


def full_core(start='2026-07-31',end='2026-11-16'):
    core=charts((start,end))
    for symbol,chart in core.items():
        chart.update({'name':symbol,'sourceUrl':'https://example.org/quotes','retrievedAt':'2026-11-17T01:30:00Z','rawSha256':'test'})
        chart['points'][end]={'close':110.,'adjustedClose':110.}
    return core


def test_refresh_recomputes_elapsed_days_markets_and_residual_without_double_count():
    c=config();c['inputs']['assetModel']=1;c['filing']['positionCount']=1;c['filing']['reportedValueUsd']=100
    rows=[{'cusip':'A','ticker':'A','issuer':'A','shares':1,'reportValueUSD':100,'valid':True,'flags':[],
           'baselineMarketValueUSD':1000000000,'currentTotalReturnValueUSD':1200000000,
           'currentMarketValueUSD':1190000000,'totalReturn':.2}]
    summary,detail=nps.build_snapshot(c,full_core(),rows,'2026-11-16',{'status':'verified','checkedAt':'2026-11-17'},'2026-11-17')
    assert summary['market']['windowDays']==108
    assert summary['inputs']['cashReturn']==pytest.approx(3*108/365)
    assert summary['inputs']['bondReturn']==pytest.approx(10)
    assert summary['inputs']['domesticBondReturn']==pytest.approx(10)
    assert summary['inputs']['fxReturn']==pytest.approx(10)
    f=summary['filing']
    assert f['base13fKRW']==pytest.approx(.1)
    assert f['base13fKRW']+f['residualBaseKRW']==pytest.approx(c['baseline']['overseas'])
    assert f['blendedReturnPct']==pytest.approx((.1*20+(c['baseline']['overseas']-.1)*10)/c['baseline']['overseas'])
    assert summary['snapshotVersion']==detail['snapshotVersion']


def test_refresh_rejects_13f_sleeve_above_total_foreign_equities():
    c=config();c['inputs']['assetModel']=1;c['filing']['positionCount']=1;c['filing']['reportedValueUsd']=100
    rows=[{'cusip':'A','ticker':'A','reportValueUSD':100,'valid':True,
           'baselineMarketValueUSD':1e15,'currentTotalReturnValueUSD':1e15}]
    with pytest.raises(ValueError,match='double count'):
        nps.build_snapshot(c,full_core(),rows,'2026-11-16',{'status':'verified'},'2026-11-17')


def test_reviewed_configuration_baseline_must_reconcile():
    c=config();nps.validate_config(c)
    c['baseline']['total']+=1
    with pytest.raises(ValueError,match='disagree'):nps.validate_config(c)


def test_current_published_snapshot_is_coherent_and_uses_declared_refresh_method():
    s=nps.load_json(ROOT/'static/data/nps/summary.json')
    d=nps.load_json(ROOT/'static/data/nps'/s['filing']['detailsFile'])
    assert s['snapshotVersion']==d['snapshotVersion']
    assert s['marketDate']==d['marketDate']
    assert s['filing']['directCount']==sum(r['method']=='direct' for r in d['rows'])
    assert s['result']['weight']==pytest.approx(nps.calculate(s['inputs'],s['assetBaseline'])['weight'])
    assert s['market']['observations']['KRW=X']['currency']=='KRW'
    obs=s['market']['observations']['KRW=X']
    assert s['inputs']['fxReturn']==pytest.approx((obs['current']['close']/obs['baseline']['close']-1)*100)
    assert s['market']['date']==s['marketDate']


def test_offline_release_check_rejects_math_drift(tmp_path):
    s=nps.load_json(ROOT/'static/data/nps/summary.json')
    d=nps.load_json(ROOT/'static/data/nps'/s['filing']['detailsFile'])
    nps.publish(s,d,tmp_path)
    assert nps.check_publication(tmp_path)['snapshotVersion']==s['snapshotVersion']
    s['result']['weight']+=1
    (tmp_path/'summary.json').write_text(json.dumps(s))
    with pytest.raises(ValueError,match='calculation mismatch'):
        nps.check_publication(tmp_path)


def test_cached_provider_future_bars_and_actions_are_excluded(tmp_path,monkeypatch):
    q=nps.quotes
    import datetime as dt
    def ts(day):return int(dt.datetime.fromisoformat(day+'T14:00:00+00:00').timestamp())
    days=['2026-06-30','2026-07-31','2026-10-16','2026-10-18']
    payload={'chart':{'result':[{'meta':{'exchangeTimezoneName':'Europe/London','currency':'USD','instrumentType':'ETF'},
      'timestamp':[ts(d) for d in days],
      'indicators':{'quote':[{'close':[100,110,120,999]}],'adjclose':[{'adjclose':[100,110,120,999]}]},
      'events':{'splits':{'later':{'date':ts('2026-10-18'),'numerator':2,'denominator':1}}}}]}}
    (tmp_path/'TEST.json').write_text(json.dumps(payload))
    monkeypatch.setattr(q,'DEADLINE',0)
    chart=q.read_chart('TEST',('2026-06-30','2026-07-31','2026-10-16'),tmp_path)
    assert chart['valid'] is True
    assert chart['prices']['current']['close']==120
    assert chart['events']['splits']==[]
    assert '2026-10-18' not in chart['points']


def test_published_split_and_corporate_action_audit_fields_are_present():
    s=nps.load_json(ROOT/'static/data/nps/summary.json')
    d=nps.load_json(ROOT/'static/data/nps'/s['filing']['detailsFile'])
    rows={r['ticker']:r for r in d['rows']}
    for ticker in ('APH','CRWD','MNST'):
        assert rows[ticker]['sharesOnCurrentBasis']>rows[ticker]['shares']
        assert rows[ticker]['splitFactorAfterReport']>1
        assert rows[ticker]['reportPriceCheck']['relativeError']==pytest.approx(0,abs=.005)
    assert rows['SCCO']['corporateActionReview']['verifiedFactor']==1.012
    assert rows['SPGI']['corporateActionReview']['decision']=='exclude'
