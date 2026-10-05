import copy
import pytest
from test_guru_rules import company, quote
from guru_extensions import evaluate_extension, technical_metrics, relative_strength, normalize_quarter, expected_quarter


def bars():
    from datetime import date, timedelta
    ds=[]; d=date(2026,10,2)
    while len(ds)<273:
        if d.weekday()<5: ds.append(d.isoformat())
        d-=timedelta(days=1)
    return [[d,100+i,101+i,99+i,1000] for i,d in enumerate(reversed(ds))]


def technical():
    value=technical_metrics(bars(),'2026-10-02')
    return {**value,'relativeStrengthPercentile':90,'rsCoverage':.95}


def test_minervini_independent_of_financial_collection_and_not_rsi():
    c=company(); c['collection']['status']='pending'; c.pop('annual')
    q=quote(); q['price']=372
    r=evaluate_extension(c,q,strategy='minervini',technical=technical())
    assert r['status']=='matched'
    assert r['metrics']['relativeStrengthPercentile']==90
    assert 'rsi14' not in r['metrics']


@pytest.mark.parametrize('change',['short','duplicate','missing','future','price','coverage'])
def test_market_data_fail_closed(change):
    b=bars()
    if change=='short': b=b[-252:]
    if change=='duplicate': b[-2][0]=b[-1][0]
    if change=='missing': b[-8][4]=None
    if change=='future': b[-1][0]='2026-10-03'
    t=technical_metrics(b,'2026-10-02')
    if change in {'short','duplicate','missing','future'}: assert t is None; return
    t.update(relativeStrengthPercentile=90,rsCoverage=.89 if change=='coverage' else .95)
    q=quote(); q['price']=373 if change=='price' else 372
    assert evaluate_extension(company(),q,strategy='minervini',technical=t)['status']=='insufficient'


def test_relative_strength_ties_and_incomplete_scope():
    rows={'a':{'return252':10},'b':{'return252':10},'c':{'return252':20}}
    relative_strength(rows,4)
    assert rows['a']['relativeStrengthPercentile']==pytest.approx(100/3)
    assert rows['c']['relativeStrengthPercentile']==pytest.approx(250/3)
    assert rows['c']['rsCoverage']==.75


def test_prior_breakout_and_volume_exclude_current_session():
    b=bars(); b[-1][1:]=[450,451,449,2000]
    t=technical_metrics(b,'2026-10-02')
    assert t['breakoutLevel']==372
    assert t['breakoutVolumeRatio']==2
    assert t['breakoutDate']=='2026-10-02'
    assert t['breakoutExtensionPct']==pytest.approx((450/372-1)*100)


def test_greenblatt_is_explicit_roa_pe_alternative():
    c=company(); c['annual'][-1]['assets']=80; q=quote(); q['price']=1728
    r=evaluate_extension(c,q,strategy='greenblatt')
    assert r['status']=='matched'
    assert r['metrics']['annualROA']==25
    assert r['metrics']['annualPE']==10
    assert r['basis']['method']=='ROA/PER 대안 · EV 매직포뮬러 아님'
    c['classification']['industry']='전기 공급업'
    assert evaluate_extension(c,q,strategy='greenblatt')['status']=='unsupported'


@pytest.mark.parametrize('mutation',['action','zero','missing','future','refresh'])
def test_greenblatt_no_synthetic_eps_assets_or_future_filings(mutation):
    c=company(); c['annual'][-1]['assets']=80
    if mutation=='action': c['epsComparability']['status']='unknown'
    if mutation=='zero': c['annual'][-1]['basicEps']=0
    if mutation=='missing': c['annual'][-1]['assets']=None
    if mutation=='future': c['sources']['2025']['equity']['filingDate']='2026-10-06'
    if mutation=='refresh': c['refreshError']='network'
    assert evaluate_extension(c,quote(),strategy='greenblatt')['status']!='matched'


def quarter_report():
    receipt='20260814001234'
    return {'year':2026,'quarter':2,'basis':'CFS','receiptNo':receipt,'filingDate':'2026-08-14',
        'periods':{'thstrm':{'start':'2026-01-01','end':'2026-06-30'}},
        'rows':[{'sj_div':'IS','account_detail':'-','account_id':aid,'account_nm':name,'currency':'KRW','rcept_no':receipt,
                 'thstrm_amount':current,'thstrm_add_amount':'999999','frmtrm_q_amount':prior}
                for aid,name,current,prior in [('ifrs-full_BasicEarningsLossPerShare','기본주당이익','200','100'),('ifrs-full_Revenue','매출액','150','100')]]}


def test_single_quarter_eps_never_subtracts_or_uses_cumulative_amount():
    q=normalize_quarter(quarter_report())
    assert q['basicEps']==200 and q['priorBasicEps']==100
    assert q['revenue']==150
    assert q['periodStart']=='2026-04-01'
    assert q['method']=='OpenDART full accounts reported three months'
    bad=quarter_report(); bad['periods']['thstrm']['start']='2026-04-01'
    assert normalize_quarter(bad) is None
    bad=quarter_report(); bad['rows'][-1]['rcept_no']='20260814009999'
    assert normalize_quarter(bad) is None


def test_oneil_requires_recent_quarter_growth_and_real_breakout():
    c=company()
    for i,r in enumerate(c['annual']): r['basicEps']=100*1.3**i
    b=bars(); b[-1][1:]=[380,381,379,2000]
    t=technical_metrics(b,'2026-10-02'); t.update(relativeStrengthPercentile=95,rsCoverage=.95)
    q=quote(); q['price']=380
    quarter=normalize_quarter(quarter_report())
    r=evaluate_extension(c,q,strategy='oneil',technical=t,quarter=quarter)
    assert r['status']=='matched'
    assert r['metrics']['quarterEpsGrowth']==100
    assert r['metrics']['quarterSalesGrowth']==50
    bad=copy.deepcopy(quarter); bad['quarter']=1
    assert evaluate_extension(c,q,strategy='oneil',technical=t,quarter=bad)['status']=='insufficient'
    bad=copy.deepcopy(quarter); bad['priorBasicEps']=0
    assert evaluate_extension(c,q,strategy='oneil',technical=t,quarter=bad)['status']=='failed'
    t['breakoutDate']=None
    assert evaluate_extension(c,q,strategy='oneil',technical=t,quarter=quarter)['status']=='failed'


def test_quarter_due_dates_do_not_call_half_year_latest_quarter():
    assert expected_quarter('2026-10-02')==(2026,2)
    assert expected_quarter('2026-11-16')==(2026,3)
    assert expected_quarter('2027-04-01')==(2026,4)


def test_extension_snapshot_counts_evidence_and_content_versions():
    from guru_snapshot import build_snapshot
    c=company(); c['annual'][-1]['assets']=80
    u=[{'symbol':c['symbol'],'name':'시험','market':'KOSPI','industry':'전자부품 제조업'}]
    q=quote();q['price']=372
    p={'tradeDate':q['date'],'stocks':[q]}; f={'companies':{c['symbol']:c}}
    # One stock percentile50 deliberately cannot pass Minervini strength>=70.
    snap,evidence=build_snapshot(u,p,f,generated_at='2026-10-05',market={'companies':{c['symbol']:{'bars':bars()}}})
    assert set(snap['strategies'])=={'buffett','lynch','oneil','minervini','greenblatt'}
    for s in snap['strategies'].values():
        assert s['universeCount']==sum(s[k+'Count'] for k in ('unsupported','pending','insufficient','failed','matched'))
    assert snap['strategies']['minervini']['failedCount']==1
    assert snap['snapshotVersion']==evidence['snapshotVersion']


def test_extension_checkpoint_merge_never_rewinds_prices_or_quarters():
    from scripts.merge_guru_extensions import merge
    current={'companies':{'s':{'tradeDate':'2026-10-02','bars':[2]}}}
    old={'companies':{'s':{'tradeDate':'2026-10-01','bars':[1]}}}
    assert merge(current,old,'market')['companies']['s']['bars']==[2]
    current={'companies':{'s':{'year':2026,'quarter':2,'checkedAt':'2026-10-05'}}}
    old={'companies':{'s':{'year':2026,'quarter':1,'checkedAt':'2026-10-06'}}}
    assert merge(current,old,'quarters')['companies']['s']['quarter']==2
    assert merge({},current,'quarters')['companies']['s']['quarter']==2


def test_rs_cohort_requires_same_date_close_but_missing_history_stays_in_denominator():
    from guru_snapshot import build_snapshot
    c=company();q=quote();q['price']=372
    u=[{'symbol':c['symbol'],'name':'시험','industry':'제조업'},{'symbol':'000001.KS','name':'종가 없음','industry':'제조업'},{'symbol':'000002.KS','name':'이력 없음','industry':'제조업'}]
    p={'tradeDate':q['date'],'stocks':[q,dict(q,symbol='000002.KS')]}
    f={'companies':{c['symbol']:c}};m={'companies':{c['symbol']:{'bars':bars()}}}
    data,_=build_snapshot(u,p,f,generated_at='2026-10-05',market=m)
    assert data['marketCoverage']['eligibleCount']==2
    assert data['marketCoverage']['observedCount']==1
    assert data['strategies']['minervini']['universeCount']==3
    assert data['strategies']['minervini']['insufficientCount']==3


def test_bad_source_quarter_cannot_publish_edited_values():
    c=company()
    for i,r in enumerate(c['annual']):r['basicEps']=100*1.3**i
    q=quote();q['price']=372;t=technical()
    quarter={**normalize_quarter(quarter_report()),'report':quarter_report()}
    quarter['basicEps']=1234
    assert evaluate_extension(c,q,strategy='oneil',technical=t,quarter=quarter)['status']=='insufficient'
