import time
from copy import deepcopy
import pytest
from scripts.generate_guru_screening import refresh_cache, DartLimit
from test_guru_financials import report


class FakeClient:
    def __init__(self, limit=False): self.requests=0; self.limit=limit
    def collect(self, row, previous):
        self.requests+=1
        if self.limit: raise DartLimit()
        from datetime import datetime, timezone
        return {'symbol': row['symbol'], 'checkedAt':datetime.now(timezone.utc).isoformat(), 'collection': {'status': 'complete'}, 'annual': []}


def test_partial_collection_checkpoint_resume():
    u=[{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(3)]
    client=FakeClient()
    first=refresh_cache(u,{},client=client,max_companies=1,max_requests=10,deadline=time.monotonic()+10)
    assert len(first['companies'])==1
    second=refresh_cache(u,first,client=client,max_companies=2,max_requests=10,deadline=time.monotonic()+10)
    assert len(second['companies'])==3
    assert client.requests==3


def test_status020_stops_requests():
    client=FakeClient(limit=True)
    result=refresh_cache([{'symbol':'000001.KS'},{'symbol':'000002.KS'},{'symbol':'000003.KS'}],{},client=client,max_companies=10,max_requests=10,deadline=time.monotonic()+10)
    assert client.requests<=2 # Only requests already in flight when a response says 020 may finish.
    assert result['collection']['status']=='rate_limited'


def test_merge_never_overwrites_newer_checked_evidence():
    from scripts.merge_guru_cache import merge_cache
    current={'companies':{'005930.KS':{'checkedAt':'2026-10-05T18:00:00+09:00','annual':[{'year':2025,'netIncome':19}]}}}
    older={'companies':{'005930.KS':{'checkedAt':'2026-10-05T17:00:00+09:00','annual':[{'year':2025,'netIncome':15}]}}}
    assert merge_cache(current,older)['companies']['005930.KS']['annual'][0]['netIncome']==19

def test_old_merge_keeps_newer_universe_metadata():
    from scripts.merge_guru_cache import merge_cache
    current={'generatedAt':'2026-10-05T18:00:00+09:00','universe':[{'symbol':'000002.KS'}]}
    old={'generatedAt':'2026-10-05T17:00:00+09:00','universe':[{'symbol':'000001.KS'}]}
    assert merge_cache(current,old)['universe']==current['universe']

def test_missing_checked_time_is_due_for_verification():
    u=[{'symbol':'000001.KS','industry':'제조업'}]; client=FakeClient()
    refresh_cache(u,{'companies':{'000001.KS':{}}},client=client,max_companies=1,max_requests=10,deadline=time.monotonic()+10)
    assert client.requests==1

def test_bounded_refresh_serves_oldest_checked_company_first():
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    u=[{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(3)]
    companies={r['symbol']:{'checkedAt':(now-timedelta(days=4+i)).isoformat()} for i,r in enumerate(u)}
    class Recorder(FakeClient):
        def collect(self,row,previous): self.selected=row['symbol'];return super().collect(row,previous)
    previous={'companies':companies}
    for expected in ['000002.KS','000001.KS','000000.KS']:
        client=Recorder(); previous=refresh_cache(u,previous,client=client,max_companies=1,max_requests=10,deadline=time.monotonic()+10)
        assert client.selected==expected

def test_major_account_dates_are_required_for_full_account_report():
    from scripts.generate_guru_screening import DartClient
    client=DartClient('test',{},10,time.monotonic()+10)
    data=report()
    def get(endpoint,params):
        if endpoint=='fnlttSinglAcntAll.json': return {'status':'000','list':data['rows']}
        return {'status':'000','list':[{'rcept_no':data['receiptNo'],'fs_div':'CFS','sj_div':'IS','thstrm_dt':'2025.07.01 ~ 2025.12.31','frmtrm_dt':'2024.01.01 ~ 2024.12.31','bfefrmtrm_dt':'2023.01.01 ~ 2023.12.31'}]}
    client.get=get
    value=client.report('test',2025,'CFS','12')
    assert value['periods']['thstrm']=={'start':'2025-07-01','end':'2025-12-31'}

def test_collection_overlaps_two_companies_but_never_more():
    import threading
    class SlowClient(FakeClient):
        def __init__(self):super().__init__();self.lock=threading.Lock();self.active=0;self.peak=0
        def collect(self,row,previous):
            with self.lock:self.active+=1;self.peak=max(self.peak,self.active)
            time.sleep(.05)
            value=super().collect(row,previous)
            with self.lock:self.active-=1
            return value
    client=SlowClient();u=[{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(5)]
    result=refresh_cache(u,{},client=client,max_companies=5,max_requests=10,deadline=time.monotonic()+10)
    assert client.peak==2
    assert len(result['companies'])==5

def test_parallel_request_budget_and_020_are_global():
    from concurrent.futures import ThreadPoolExecutor
    from scripts.generate_guru_screening import DartClient,BudgetLimit
    import threading
    calls=[];lock=threading.Lock()
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'status':'000'}
    class Session:
        def get(self,*a,**kw):
            with lock:calls.append(1)
            time.sleep(.01);return Response()
    client=DartClient('test',{},5,time.monotonic()+10)
    client.session=Session()
    client._get_session=lambda:Session()
    def request():
        try:return client.get('test',{})
        except BudgetLimit:return None
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:request(),range(10)))
    assert len(calls)==client.requests==5
    class Limited(Response):
        def json(self):return {'status':'020'}
    class LimitedSession(Session):
        def get(self,*a,**kw):return Limited()
    client=DartClient('test',{},5,time.monotonic()+10);client.session=LimitedSession();client._get_session=lambda:LimitedSession()
    for _ in range(2):
        try:client.get('test',{})
        except DartLimit:pass
    assert client.requests==1


def test_collector_uses_authoritative_dates_without_company_profile_request():
    from scripts.generate_guru_screening import DartClient
    client=DartClient('test',{'000001':{'corpCode':'00000001'}},20,time.monotonic()+10)
    client.get=lambda *a: (_ for _ in ()).throw(AssertionError('No acc_mt profile request needed'))
    client.report=lambda *a:report()
    client.actions=lambda *a:{'status':'verified','events':[]}
    value=client.collect({'symbol':'000001.KS','industry':'제조업'},None)
    assert value['reports']


def test_refresh_does_not_delay_companies_for_upfront_bulk_requests():
    class IndividuallyVerified(FakeClient):
        def prefetch_periods(self,*args):raise AssertionError('Live bulk prefetch exhausted most of the deadline')
    client=IndividuallyVerified()
    result=refresh_cache([{'symbol':'000001.KS','industry':'제조업'}],{},client=client,max_companies=1,max_requests=10,deadline=time.monotonic()+10)
    assert result['collection']['attempted']==1


def action_client(total=2100, *, mutate=None, max_requests=30, max_seconds=10):
    from scripts.generate_guru_screening import DartClient
    calls=[]
    class Response:
        def __init__(self,packet):self.packet=packet
        def raise_for_status(self):pass
        def json(self):return self.packet
    class Session:
        def get(self,url,params,timeout):
            page=params['page_no'];calls.append(page)
            start=(page-1)*100
            rows=[{'corp_code':'00126380','rcept_no':f'20260301{i:06}',
                   'rcept_dt':'20261007','report_nm':'대량보유상황보고서'}
                  for i in range(start,min(start+100,total))]
            if rows and page==(total+99)//100:rows[-1]['report_nm']='주식분할결정'
            packet={'status':'000','page_no':page,'page_count':100,
                    'total_count':total,'total_page':(total+99)//100,'list':rows}
            if mutate:mutate(packet,page)
            return Response(packet)
    client=DartClient('fake',{},max_requests,time.monotonic()+max_seconds)
    client._get_session=lambda:Session()
    return client,calls


def test_full_action_review_passes_twenty_pages_and_checks_the_last_event():
    client,calls=action_client()
    result=client.actions('00126380','005930.KS','2022-01-01','2026-10-08')
    assert calls==list(range(1,22))
    assert result['status']=='verified'
    assert result['events']==[{'date':'20261007','name':'주식분할결정','receiptNo':'20260301002099'}]
    # The reception date and receipt identifier prefix intentionally differ.
    assert client.requests==21


@pytest.mark.parametrize('invalid', ['partial013','wrongpage','count','total','corp','receipt','date','duplicate','name'])
def test_full_action_review_never_certifies_partial_or_malformed_pagination(invalid):
    from scripts.generate_guru_screening import ProviderError
    def mutate(packet,page):
        if page!=2:return
        if invalid=='partial013':packet.clear();packet['status']='013';return
        if invalid=='wrongpage':packet['page_no']=1
        if invalid=='count':packet['list']=[]
        if invalid=='total':packet['total_count']+=1
        if invalid=='corp':packet['list'][0]['corp_code']='99999999'
        if invalid=='receipt':packet['list'][0]['rcept_no']='bad'
        if invalid=='date':packet['list'][0]['rcept_dt']='20260230'
        if invalid=='duplicate':packet['list'][0]['rcept_no']='20260301000000'
        if invalid=='name':packet['list'][0]['report_nm']=''
    client,calls=action_client(total=101,mutate=mutate)
    with pytest.raises(ProviderError,match='pagination verification failed'):
        client.actions('00126380','005930.KS','2022-01-01','2026-10-08')
    assert calls==[1,2]


@pytest.mark.parametrize('stop', ['requests','deadline','020'])
def test_full_action_review_keeps_shared_budget_and_rate_limit_stops(stop):
    from scripts.generate_guru_screening import BudgetLimit
    def mutate(packet,page):
        if stop=='020' and page==3:packet.clear();packet['status']='020'
    client,calls=action_client(max_requests=3,mutate=mutate)
    if stop=='deadline':client.deadline=time.monotonic()-1
    with pytest.raises(DartLimit if stop=='020' else BudgetLimit):
        client.actions('00126380','005930.KS','2022-01-01','2026-10-08')
    assert len(calls)==(0 if stop=='deadline' else 3)
    if stop=='020':
        with pytest.raises(DartLimit):client.get('list.json',{})
        assert len(calls)==3


def test_empty_initial_action_review_is_distinct_from_partial_no_data():
    client,_=action_client()
    client.get=lambda *args:{'status':'013'}
    assert client.actions('00126380','005930.KS','2022-01-01','2026-10-08')['status']=='verified'


def test_selected_retry_overrides_only_its_daily_cooldown_and_preserves_all_other_companies():
    from datetime import datetime,timezone
    universe=[{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(3)]
    before={'companies':{r['symbol']:{'symbol':r['symbol'],'checkedAt':datetime.now(timezone.utc).isoformat(),'annual':[{'year':2025,'basicEps':100+i}]} for i,r in enumerate(universe)}}
    untouched=deepcopy(before);client=FakeClient()
    result=refresh_cache(universe,before,client=client,max_companies=1,max_requests=10,
                         deadline=time.monotonic()+10,symbols=['000001.KS'])
    assert before==untouched
    assert client.requests==result['collection']['attempted']==1
    assert set(result['companies'])==set(before['companies'])
    for symbol in ['000000.KS','000002.KS']:assert result['companies'][symbol]==before['companies'][symbol]


def test_invalid_selected_symbol_fails_before_any_company_request():
    client=FakeClient()
    with pytest.raises(ValueError,match='current KIND universe'):
        refresh_cache([{'symbol':'000001.KS'}],{},client=client,max_companies=5,max_requests=10,
                      deadline=time.monotonic()+10,symbols=['999999.KS'])
    assert client.requests==0


def test_selected_retry_respects_company_budget_and_preserves_unselected_due_rows():
    from datetime import datetime,timedelta,timezone
    universe=[{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(4)]
    before={'companies':{r['symbol']:{'checkedAt':(datetime.now(timezone.utc)-timedelta(days=5)).isoformat(),'annual':[{'year':2025}]} for r in universe}}
    result=refresh_cache(universe,before,client=FakeClient(),max_companies=1,max_requests=10,
                         deadline=time.monotonic()+10,symbols=['000001.KS','000002.KS'])
    assert result['collection']['attempted']==1 and result['collection']['status']=='partial'
    for symbol in ['000000.KS','000003.KS']:assert result['companies'][symbol]==before['companies'][symbol]


def test_symbols_cli_selects_one_fresh_company_without_global_scan_or_cache_loss(monkeypatch):
    from datetime import datetime,timezone
    import scripts.generate_guru_screening as module
    import scripts.generate_screener as screener
    universe=[{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(2)]
    previous={'universe':universe,'companies':{r['symbol']:{'symbol':r['symbol'],'checkedAt':datetime.now(timezone.utc).isoformat(),'annual':[{'year':2025}]} for r in universe}}
    monkeypatch.setenv('DART_API_KEY','fake')
    monkeypatch.setattr(module.sys,'argv',['collector','--collect','--refresh-actions','--symbols','000001.KS'])
    monkeypatch.setattr(screener,'load_universe',lambda:universe)
    monkeypatch.setattr(module,'load_json',lambda path,default:deepcopy(previous) if path.name=='guru_financials.json' else {})
    client=FakeClient()
    monkeypatch.setattr(module,'DartClient',lambda *args:client)
    monkeypatch.setattr(module,'refresh_action_windows',lambda *args,**kwargs:pytest.fail('Targeted full review must not start a global action scan'))
    writes=[]
    monkeypatch.setattr(module,'atomic_json',lambda path,value:writes.append((path.name,deepcopy(value))))
    def build(current,prices,cache,**kwargs):
        assert current==universe and cache['universe']==universe
        assert cache['companies']['000000.KS']==previous['companies']['000000.KS']
        assert set(cache['companies'])=={'000000.KS','000001.KS'}
        return {'tradeDate':'2026-10-07','snapshotVersion':'test','collection':cache['collection'],'strategies':{}},{}
    monkeypatch.setattr(module,'build_snapshot',build)
    monkeypatch.setattr(module,'publish_snapshot',lambda *args:None)
    module.main()
    assert client.requests==1 and writes


@pytest.mark.parametrize('symbols', ['999999.KS','bad','000001.KS,'])
def test_symbols_cli_rejects_unknown_or_malformed_requests_before_dart_collection(monkeypatch,symbols):
    import scripts.generate_guru_screening as module
    import scripts.generate_screener as screener
    monkeypatch.setenv('DART_API_KEY','fake')
    monkeypatch.setattr(module.sys,'argv',['collector','--collect','--symbols',symbols])
    monkeypatch.setattr(module,'load_json',lambda *args:{})
    monkeypatch.setattr(screener,'load_universe',lambda:[{'symbol':'000001.KS'}])
    monkeypatch.setattr(module,'DartClient',lambda *args:pytest.fail('Invalid selection must not create a DART client'))
    with pytest.raises(SystemExit) as error:module.main()
    assert error.value.code==2
