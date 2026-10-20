"""Disclosure-aligned multiasset estimates: no invented private NAV or cash income."""
import copy
import datetime as dt
import importlib.util
import json
import math
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nps_realism_pipeline',ROOT/'scripts/nps_pipeline.py')
nps=importlib.util.module_from_spec(spec);spec.loader.exec_module(nps)

def config():return nps.load_json(ROOT/'scripts/nps/config.json')
def core_prices():
    core={s:{'currency':currency,'name':s,'sourceUrl':'https://example.org/quote','retrievedAt':'2026-10-18','rawSha256':'a',
      'points':{'2026-07-31':{'close':100.,'adjustedClose':100.},'2026-10-16':{'close':101.,'adjustedClose':101.}}} for s,currency in nps.CORE.items()}
    core['273130.KS']['points']['2026-10-16']['adjustedClose']=98.
    return core

def snapshot(c=None,core=None):
    c=c or config();c=copy.deepcopy(c);c['filing'].update(positionCount=1,reportedValueUsd=100)
    core=core if core is not None else core_prices()
    rows=[{'cusip':'A','ticker':'A','issuer':'A','shares':1,'reportValueUSD':100,'valid':True,'flags':[],
      'baselineMarketValueUSD':1e9,'currentTotalReturnValueUSD':1.01e9,'currentMarketValueUSD':1.01e9,'totalReturn':.01}]
    return nps.build_snapshot(c,core,rows,'2026-10-16',{'status':'verified'},'2026-10-18')

def test_new_core_requires_credit_cash_unhedged_bonds_and_alternative_proxies():
    assert {s:nps.CORE[s] for s in ['273130.KS','357870.KS','BIL','AGGG.L','PSP','REET','IGF']}==dict(zip(['273130.KS','357870.KS','BIL','AGGG.L','PSP','REET','IGF'],['KRW','KRW','USD','USD','USD','USD','USD']))

def test_realism_uses_totalreturn_credit_bonds_no_second_yield_or_alternative_carry():
    s,d=snapshot()
    assert s['inputs']['assetModel']==2
    assert s['inputs']['domesticBondReturn']==pytest.approx(-2)
    assert s['inputs']['alternativeReturn']==0
    assert s['realism']['alternatives']['economicProxyReturnPct']==pytest.approx(1)
    assert s['snapshotVersion']==d['snapshotVersion']
    assert s['result']['cashBreakdown']['shortTermBase']==pytest.approx(5.1381)
    assert s['result']['cashBreakdown']['nonFinancialBase']==pytest.approx(.9857)
    assert s['result']['cashBreakdown']['reconciliationBase']==pytest.approx(1.7346)

def test_external_flow_excludes_investment_income_and_uses_elapsed_days():
    s,_=snapshot()
    expected=(39493.03145481+10.2624-32461.746821756)/1000/212*77
    assert s['inputs']['netFlow']==pytest.approx(expected)
    assert s['realism']['externalFlows']['observedNetFlow']==pytest.approx(7.041547033054)
    assert s['inputs']['domesticFlow']==0
    assert s['result']['cashBreakdown']['externalFlowIncome']==pytest.approx(expected*.5*.01)

def test_cash_group_only_deposit_receives_interest_and_scenarios_recompute_hedge_flow():
    c=config();s=copy.deepcopy(c['inputs']);s.update(cashIncomeReturn=2,hedgeCarryReturn=-1,hedgeRatio=15,netFlow=3,otherReturn=0)
    r=nps.calculate(s,c['assetBaseline']);b=r['cashBreakdown']
    foreign=sum(a['base']*a['foreignShare'] for a in c['assetBaseline'])
    assert b['shortTermIncome']==pytest.approx(5.1381*.02)
    assert b['hedgeCarry']==pytest.approx(foreign*.15*-.01)
    assert b['externalFlowIncome']==pytest.approx(3*.5*.02)
    cash=next(a for a in r['assets'] if a['id']=='cash')
    assert cash['marketGain']==pytest.approx(b['shortTermIncome']+b['hedgeCarry']+b['externalFlowIncome'])
    legacy=nps.calculate({**s,'assetModel':1,'cashReturn':cash['returnPercent']},c['assetBaseline'])
    assert legacy['weight']==pytest.approx(r['weight'])
    zero=nps.calculate({**s,'hedgeRatio':0,'netFlow':0},c['assetBaseline'])
    assert zero['cashBreakdown']['hedgeCarry']==zero['cashBreakdown']['externalFlowIncome']==0

def test_model_sensitive_metadata_changes_version_even_with_same_market_inputs():
    c=config();first,_=snapshot(c);c['assetBaseline'][3]['foreignShare']-=.01;second,_=snapshot(c)
    assert first['snapshotVersion']!=second['snapshotVersion']
    c=config();c['realism']['domesticBonds']['proxyDuration']=5.22;third,_=snapshot(c)
    assert first['snapshotVersion']!=third['snapshotVersion']

def test_sensitivity_cases_are_explicit_one_factor_assumptions_and_not_confidence_interval():
    s,_=snapshot();sense=s['sensitivity'];assert sense['kind']=='assumption-cases'
    cases=sense['cases'];assert len(cases)==8
    for case in cases:
        assert len(case['patch'])==1
        expected=nps.calculate({**s['inputs'],**case['patch']},s['assetBaseline'])
        assert case['weight']==pytest.approx(expected['weight'])
    assert {case['id'] for case in cases}=={'beta-low','beta-high','hedge-none','hedge-high','flows-none','flows-double','bond-unhedged-proxy','alternative-economic-proxy'}

def test_monthly_parser_only_reads_monthly_portfolio_notice_not_later_other_notices():
    html='<div>2026년 10월 말 기준</div><span>자산군별 포트폴리오 운용 현황 및 수익률(2026.7월)</span><span>2026/09/29</span>'
    assert nps.realism.monthly_report_date(html)=='2026-07-31'
    assert nps.realism.monthly_report_date(html.replace('2026.7월','2026.8월'))=='2026-08-31'
    with pytest.raises(ValueError):nps.realism.monthly_report_date('2026년 10월 투자정보')

def test_official_check_new_month_is_review_required_and_network_failure_explicit(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return '자산군별 포트폴리오 운용 현황 및 수익률(2026.8월)'.encode()
    monkeypatch.setattr(nps.realism.urllib.request,'urlopen',lambda *a,**k:Response())
    result=nps.realism.monthly_check(config(),float('inf'))
    assert result['status']=='review-required' and result['reportDate']=='2026-08-31'
    def failed(*a,**k):raise OSError('unavailable')
    monkeypatch.setattr(nps.realism.urllib.request,'urlopen',failed)
    assert nps.realism.monthly_check(config(),float('inf'))['status']=='unavailable'

def test_reviewed_cash_split_and_alternative_composition_must_reconcile():
    c=config();nps.validate_config(c)
    c['realism']['cash']['reconciliationBase']+=1
    with pytest.raises(ValueError,match='components'):nps.validate_config(c)
    c=config();c['inputs']['cashWeight']=1
    with pytest.raises(ValueError,match='weights disagree'):nps.validate_config(c)
    c=config();c['realism']['alternatives']['composition'][0]['weightPct']+=1
    with pytest.raises(ValueError,match='composition'):nps.validate_config(c)

def test_cash_weights_scale_with_baseline_and_never_credit_interest_to_nonfinancial():
    c=config();s={**c['inputs'],'cashIncomeReturn':5,'hedgeCarryReturn':0,'netFlow':0,'otherReturn':0}
    first=nps.calculate(s,c['assetBaseline'])
    s['baseTotal']=s['baseDomestic']+2*(s['baseTotal']-s['baseDomestic'])
    second=nps.calculate(s,c['assetBaseline'])
    for key in ('shortTermBase','nonFinancialBase','reconciliationBase','shortTermIncome','hedgePrincipal'):
        assert second['cashBreakdown'][key]==pytest.approx(first['cashBreakdown'][key]*2)
    assert first['cashBreakdown']['shortTermIncome']==pytest.approx(5.1381*.05)
    for patch in ({'cashWeight':1.1},{'cashNonFinancialWeight':1},{'flowIncomeFraction':-1},{'cashIncomeReturn':-100}):
        with pytest.raises(ValueError):nps.calculate({**s,**patch},c['assetBaseline'])

def test_required_proxy_missing_or_wrong_currency_never_creates_partial_common_close():
    s,d=snapshot()
    core={symbol:{'currency':currency,'points':{'2026-07-31':{'close':1,'adjustedClose':1},'2026-10-16':{'close':1,'adjustedClose':1}}} for symbol,currency in nps.CORE.items()}
    for symbol in set(nps.CORE)-{'AGGG.L'}:
        altered=copy.deepcopy(core);altered[symbol]['points'].pop('2026-07-31')
        with pytest.raises(ValueError,match='baseline'):nps.common_session(altered,'2026-10-16','2026-07-31')
        altered=copy.deepcopy(core);altered[symbol]['currency']='GBP'
        with pytest.raises(ValueError,match='currency'):nps.common_session(altered,'2026-10-16','2026-07-31')
        altered=copy.deepcopy(core);altered[symbol]['points'].pop('2026-10-16')
        with pytest.raises(ValueError,match='No common'):nps.common_session(altered,'2026-10-16','2026-07-31')

def test_core_collection_failure_preserves_last_valid_files(tmp_path,monkeypatch):
    from types import SimpleNamespace
    current=nps.load_json(ROOT/'static/data/nps/summary.json')
    detail=nps.load_json(ROOT/'static/data/nps'/current['filing']['detailsFile'])
    nps.publish(current,detail,tmp_path)
    original=(tmp_path/'summary.json').read_bytes()
    def read(symbol,dates,cache,refresh):
        if symbol=='273130.KS':raise ValueError('required proxy unavailable')
        return {'currency':nps.CORE[symbol],'points':{d:{'close':1,'adjustedClose':1} for d in dates}}
    monkeypatch.setattr(nps.quotes,'read_chart',read)
    args=SimpleNamespace(config=nps.CONFIG,output_dir=tmp_path,check=False,as_of='2026-10-16',force=True,max_seconds=600,cache_dir=tmp_path/'cache',workers=4)
    with pytest.raises(ValueError,match='required proxy'):nps.run(args)
    assert (tmp_path/'summary.json').read_bytes()==original
    assert (tmp_path/current['filing']['detailsFile']).read_text()==nps.canonical(detail)+'\n'

def test_offline_check_validates_cash_components_and_recomputed_scenarios(tmp_path):
    summary,detail=snapshot();nps.publish(summary,detail,tmp_path)
    nps.check_publication(tmp_path)
    summary['result']['cashBreakdown']['nonFinancialBase']+=1
    (tmp_path/'summary.json').write_text(nps.canonical(summary))
    with pytest.raises(ValueError,match='cash breakdown'):nps.check_publication(tmp_path)
    summary,detail=snapshot();summary['sensitivity']['cases'][0]['weight']+=1
    nps.publish(summary,detail,tmp_path)
    with pytest.raises(ValueError,match='assumption-case'):nps.check_publication(tmp_path)

@pytest.mark.parametrize('notice',['자산군별 포트폴리오 운용 현황 및 수익률(2099.12월)',
    '자산군별 포트폴리오 운용 현황 및 수익률(2026.13월)', '',
    '자산군별 포트폴리오 운용 현황 및 수익률(2026.월)',
    '자산군별 포트폴리오 운용 현황 및 수익률(2026.7월 미확인)'])
def test_monthly_check_future_or_malformed_notice_is_unavailable_and_keeps_baseline(monkeypatch,notice):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return notice.encode()
    monkeypatch.setattr(nps.realism.urllib.request,'urlopen',lambda *a,**k:Response())
    result=nps.realism.monthly_check(config(),float('inf'))
    assert result['status']=='unavailable'
    assert result['reportDate']==result['baselineDate']==config()['baseline']['date']
    assert result.get('reason')

@pytest.mark.parametrize('event,manual_force,expected',[
    ('push',False,True),('schedule',False,False),
    ('workflow_dispatch',False,False),('workflow_dispatch',True,True)])
def test_source_push_forces_same_market_date_recheck_but_schedule_preserves_skip(event,manual_force,expected):
    import re
    workflow=(ROOT/'.github/workflows/update-nps.yml').read_text()
    expression=re.search(r'FORCE_RECHECK:\s*\$\{\{(.*?)\}\}',workflow).group(1)
    expression=expression.replace('github.event_name',repr(event)).replace('inputs.force',repr(manual_force))
    expression=expression.replace('&&',' and ').replace('||',' or ')
    assert bool(eval(expression,{'__builtins__':{}})) is expected

def test_source_push_filter_includes_all_nps_modules():
    from fnmatch import fnmatchcase
    import re
    workflow=(ROOT/'.github/workflows/update-nps.yml').read_text()
    push=workflow.split('  push:\n',1)[1].split('  workflow_dispatch:',1)[0]
    paths=re.findall(r"      - '([^']+)'",push)
    for source in ('scripts/nps_pipeline.py','scripts/nps/config.json','scripts/nps/quotes.py',
                   'scripts/nps/realism.py','scripts/nps/new_proxy.py'):
        assert any(fnmatchcase(source,path) for path in paths),source

def test_optional_unhedged_proxy_does_not_rewind_other_twelve_common_closes():
    core=core_prices()
    for symbol in set(nps.CORE)-{'AGGG.L'}:
        core[symbol]['points']['2026-10-19']={'close':102.,'adjustedClose':102.}
    assert nps.common_session(core,'2026-10-19','2026-07-31')=='2026-10-19'
    del core['AGGG.L']
    assert nps.common_session(core,'2026-10-19','2026-07-31')=='2026-10-19'

@pytest.mark.parametrize('failure',['missing-current','missing-baseline','null-close','zero-adjusted',
    'negative-close','nan-adjusted','infinite-close','wrong-currency','fetch-error'])
def test_unavailable_unhedged_proxy_omits_only_comparison_and_preserves_central_mark(failure,tmp_path):
    complete,_=snapshot();core=core_prices();proxy=core['AGGG.L']
    if failure=='missing-current':del proxy['points']['2026-10-16']
    elif failure=='missing-baseline':del proxy['points']['2026-07-31']
    elif failure=='null-close':proxy['points']['2026-10-16']['close']=None
    elif failure=='zero-adjusted':proxy['points']['2026-10-16']['adjustedClose']=0
    elif failure=='negative-close':proxy['points']['2026-10-16']['close']=-1
    elif failure=='nan-adjusted':proxy['points']['2026-10-16']['adjustedClose']=float('nan')
    elif failure=='infinite-close':proxy['points']['2026-10-16']['close']=float('inf')
    elif failure=='wrong-currency':proxy['currency']='GBP'
    elif failure=='fetch-error':proxy.update(points={},currency=None,error='AGGG provider unavailable')
    summary,detail=snapshot(core=core)
    assert summary['inputs']==complete['inputs'] and summary['result']==complete['result']
    bonds=summary['realism']['overseasBonds']
    assert bonds['unhedgedProxyReturnPct'] is None
    assert bonds['unhedgedProxyStatus']=='unavailable' and bonds['unhedgedProxyDate']=='2026-10-16'
    assert len(summary['sensitivity']['cases'])==7
    assert 'bond-unhedged-proxy' not in {case['id'] for case in summary['sensitivity']['cases']}
    assert summary['sensitivity']['unavailable']==[{'id':'bond-unhedged-proxy','label':'해외채권 AGGG 비헤지 대용지표',
        'reason':'동일 기준일의 가격을 확인하지 못해 비교를 제공하지 않아요.'}]
    observed=summary['market']['observations']['AGGG.L']
    assert observed['sourceUrl']==proxy['sourceUrl'] and observed['status']=='unavailable'
    assert observed['error'] and ('미확인' in next(s['detail'] for s in summary['sources'] if s['title'].startswith('AGGG.L')))
    if failure=='missing-current':assert observed['current'] is None
    if failure=='wrong-currency':assert observed['currency']=='GBP'
    if failure=='fetch-error':assert observed['error']=='AGGG provider unavailable'
    nps.publish(summary,detail,tmp_path)
    assert nps.check_publication(tmp_path)['snapshotVersion']==summary['snapshotVersion']

@pytest.mark.parametrize('adjusted_close',[100.,101.])
def test_available_unhedged_proxy_keeps_eight_scenarios_and_dated_status(adjusted_close):
    core=core_prices();core['AGGG.L']['points']['2026-10-16']['adjustedClose']=adjusted_close
    summary,_=snapshot(core=core);bonds=summary['realism']['overseasBonds']
    assert bonds['unhedgedProxyStatus']=='available' and bonds['unhedgedProxyDate']=='2026-10-16'
    assert bonds['unhedgedProxyReturnPct']==pytest.approx(adjusted_close-100)
    assert len(summary['sensitivity']['cases'])==8
    assert not summary['sensitivity'].get('unavailable')

@pytest.fixture
def collection(tmp_path,monkeypatch):
    from types import SimpleNamespace
    c=config();c['filing'].update(positionCount=1,reportedValueUsd=100)
    c['holdings']=[{'cusip':'A','ticker':'A','issuer':'A','shares':1,'valueUsd':100}]
    path=tmp_path/'config.json';path.write_text(nps.canonical(c))
    state=SimpleNamespace(core=core_prices(),proxy_error=True,filing_checks=0)
    def read(symbol,dates,cache,refresh):
        if symbol=='AGGG.L' and state.proxy_error:raise OSError('AGGG provider unavailable')
        if symbol in state.core:return state.core[symbol]
        return {'valid':True,'flags':[],'prices':{'report':{'close':100.},'baseline':{'close':100.},'current':{'close':101.}},
            'events':{'splits':[],'dividends':[]},'totalReturn':.01}
    def check(*a):
        state.filing_checks+=1
        return {'status':'verified'}
    monkeypatch.setattr(nps.quotes,'read_chart',read)
    monkeypatch.setattr(nps,'filing_check',check)
    monkeypatch.setattr(nps.realism,'monthly_check',lambda *a:{'status':'verified'})
    state.args=SimpleNamespace(config=path,output_dir=tmp_path/'published',check=False,as_of='2026-10-18',
        force=True,max_seconds=600,cache_dir=tmp_path/'cache',workers=1)
    return state

def test_optional_proxy_fetch_failure_publishes_central_close_without_invented_observations(collection):
    args=collection.args
    nps.run(args)
    summary=nps.load_json(args.output_dir/'summary.json')
    assert summary['marketDate']=='2026-10-16'
    assert summary['realism']['overseasBonds']['unhedgedProxyReturnPct'] is None
    observed=summary['market']['observations']['AGGG.L']
    assert observed['baseline'] is None and observed['current'] is None and observed['currency'] is None
    assert observed['error']=='AGGG provider unavailable' and 'AGGG.L' in observed['sourceUrl']
    assert nps.check_publication(args.output_dir)['snapshotVersion']==summary['snapshotVersion']

@pytest.mark.parametrize('cutoff',['2026-10-16','2026-10-18'])
def test_schedule_recovers_missing_comparison_on_same_market_date_then_skips(collection,cutoff):
    args=collection.args;args.force=False;args.as_of=cutoff
    nps.run(args);before=nps.load_json(args.output_dir/'summary.json')
    assert before['realism']['overseasBonds']['unhedgedProxyStatus']=='unavailable'
    collection.proxy_error=False
    nps.run(args);recovered=nps.load_json(args.output_dir/'summary.json')
    assert recovered['realism']['overseasBonds']['unhedgedProxyStatus']=='available'
    assert recovered['marketDate']==before['marketDate'] and recovered['snapshotVersion']!=before['snapshotVersion']
    assert recovered['inputs']==before['inputs'] and recovered['result']==before['result']
    original=(args.output_dir/'summary.json').read_bytes();checks=collection.filing_checks
    nps.run(args)
    assert (args.output_dir/'summary.json').read_bytes()==original
    assert collection.filing_checks==checks

def test_comparison_retry_never_replaces_newer_central_market_date(collection):
    args=collection.args;args.force=False;args.as_of='2026-10-19'
    for symbol in set(nps.CORE)-{'AGGG.L'}:
        collection.core[symbol]['points']['2026-10-19']={'close':102.,'adjustedClose':102.}
    nps.run(args);original=(args.output_dir/'summary.json').read_bytes()
    for symbol in set(nps.CORE)-{'AGGG.L'}:del collection.core[symbol]['points']['2026-10-19']
    with pytest.raises(ValueError,match='newer market snapshot'):nps.run(args)
    assert (args.output_dir/'summary.json').read_bytes()==original

def test_published_refresh_description_matches_retry_schedule_and_source_recalculation():
    summary,_=snapshot();update=summary['update']
    for clock in ('10:30','13:30','16:30'):assert clock in update['frequency']
    assert update['retryScheduleUTC']==['30 4 * * 2-6','30 7 * * 2-6']
    assert '같은 시장일' in update['sourceRefresh'] and '강제 재계산' in update['sourceRefresh']

def test_offline_assumption_check_accepts_last_bit_result_roundoff(tmp_path):
    summary,detail=snapshot()
    for case in summary['sensitivity']['cases']:
        for key in ('weight','gap','adjustment'):case[key]=math.nextafter(case[key],math.inf)
    for key in ('lowWeight','highWeight','lowAdjustment','highAdjustment'):
        summary['sensitivity'][key]=math.nextafter(summary['sensitivity'][key],math.inf)
    nps.publish(summary,detail,tmp_path)
    assert nps.check_publication(tmp_path)['snapshotVersion']==summary['snapshotVersion']

@pytest.mark.parametrize('key',['weight','gap','adjustment','lowWeight','highWeight','lowAdjustment','highAdjustment'])
def test_offline_assumption_check_rejects_material_numeric_drift(tmp_path,key):
    summary,detail=snapshot()
    target=summary['sensitivity']['cases'][0] if key in ('weight','gap','adjustment') else summary['sensitivity']
    target[key]+=1e-5
    nps.publish(summary,detail,tmp_path)
    with pytest.raises(ValueError,match='assumption-case'):nps.check_publication(tmp_path)

@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf'),True,'0'])
def test_offline_assumption_check_rejects_nonfinite_or_nonnumeric_result(tmp_path,value):
    summary,detail=snapshot();nps.publish(summary,detail,tmp_path)
    summary['sensitivity']['cases'][0]['weight']=value
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='assumption-case'):nps.check_publication(tmp_path)

@pytest.mark.parametrize('tamper',['missing-number','extra-number','renamed-number','id','label','kind','note',
    'patch-last-bit','patch-key','patch-type','missing-case','case-order','cases-type','missing-sensitivity'])
def test_offline_assumption_check_keeps_structure_and_economic_patch_exact(tmp_path,tamper):
    summary,detail=snapshot();sensitivity=summary['sensitivity'];case=sensitivity['cases'][0]
    if tamper=='missing-number':del case['weight']
    elif tamper=='extra-number':case['unexpected']=0
    elif tamper=='renamed-number':case['otherWeight']=case.pop('weight')
    elif tamper=='id':case['id']='other-case'
    elif tamper=='label':case['label']+=' changed'
    elif tamper=='kind':sensitivity['kind']='confidence-interval'
    elif tamper=='note':sensitivity['note']='changed assumptions'
    elif tamper=='patch-last-bit':case['patch']['beta']=math.nextafter(case['patch']['beta'],math.inf)
    elif tamper=='patch-key':case['patch']['netFlow']=0
    elif tamper=='patch-type':case['patch']['beta']=str(case['patch']['beta'])
    elif tamper=='missing-case':sensitivity['cases'].pop()
    elif tamper=='case-order':sensitivity['cases'].reverse()
    elif tamper=='cases-type':sensitivity['cases']={}
    elif tamper=='missing-sensitivity':del summary['sensitivity']
    nps.publish(summary,detail,tmp_path)
    with pytest.raises(ValueError,match='assumption-case'):nps.check_publication(tmp_path)

@pytest.mark.parametrize('tamper',['missing','id','label','reason','extra-field'])
def test_offline_assumption_check_keeps_unavailable_comparison_metadata_exact(tmp_path,tamper):
    core=core_prices();del core['AGGG.L']['points']['2026-10-16']
    summary,detail=snapshot(core=core);unavailable=summary['sensitivity']['unavailable']
    if tamper=='missing':del summary['sensitivity']['unavailable']
    elif tamper=='extra-field':unavailable[0]['weight']=0
    else:unavailable[0][tamper]='changed'
    nps.publish(summary,detail,tmp_path)
    with pytest.raises(ValueError,match='assumption-case'):nps.check_publication(tmp_path)
