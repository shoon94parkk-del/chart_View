import time
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


def test_batch_periods_use_at_most_100_companies_and_match_receipts():
    from scripts.generate_guru_screening import DartClient
    codes={f'{i:06}':{'corpCode':f'{i:08}'} for i in range(201)}
    client=DartClient('test',codes,20,time.monotonic()+10)
    calls=[];data=report()
    def get(endpoint,params):
        calls.append((endpoint,params))
        if endpoint=='fnlttMultiAcnt.json':
            return {'status':'000','list':[{'stock_code':f'{int(c):06}','rcept_no':data['receiptNo'],'fs_div':'CFS','sj_div':'IS',
                'thstrm_dt':'2025.01.01 ~ 2025.12.31'} for c in params['corp_code'].split(',')]}
        if endpoint=='fnlttSinglAcntAll.json':return {'status':'000','list':data['rows']}
        raise AssertionError('Matching batch periods must avoid single-company date requests')
    client.get=get
    client.prefetch_periods([{'symbol':f'{i:06}.KS','industry':'제조업'} for i in range(201)],2025)
    assert len(calls)==6
    assert all(len(p['corp_code'].split(','))<=100 for _,p in calls)
    value=client.report('00000001',2025,'CFS','')
    assert value['periods']['thstrm']=={'start':'2025-01-01','end':'2025-12-31'}
    assert len(calls)==7


def test_batch_stale_receipt_falls_back_to_same_receipt_single_dates():
    from scripts.generate_guru_screening import DartClient
    client=DartClient('test',{'000001':{'corpCode':'00000001'}},20,time.monotonic()+10)
    data=report();calls=[]
    def get(endpoint,params):
        calls.append(endpoint)
        if endpoint=='fnlttMultiAcnt.json':return {'status':'000','list':[{'stock_code':'000001','rcept_no':'20260301000001','fs_div':'CFS','sj_div':'IS','thstrm_dt':'2025.01.01 ~ 2025.12.31'}]}
        if endpoint=='fnlttSinglAcntAll.json':return {'status':'000','list':data['rows']}
        return {'status':'000','list':[{'rcept_no':data['receiptNo'],'fs_div':'CFS','sj_div':'IS','thstrm_dt':'2025.07.01 ~ 2025.12.31'}]}
    client.get=get
    client.prefetch_periods([{'symbol':'000001.KS','industry':'제조업'}],2025)
    value=client.report('00000001',2025,'CFS','')
    assert calls[-1]=='fnlttSinglAcnt.json'
    assert value['periods']['thstrm']['start']=='2025-07-01'


def test_collector_uses_authoritative_dates_without_company_profile_request():
    from scripts.generate_guru_screening import DartClient
    client=DartClient('test',{'000001':{'corpCode':'00000001'}},20,time.monotonic()+10)
    client.get=lambda *a: (_ for _ in ()).throw(AssertionError('No acc_mt profile request needed'))
    client.report=lambda *a:report()
    client.actions=lambda *a:{'status':'verified','events':[]}
    value=client.collect({'symbol':'000001.KS','industry':'제조업'},None)
    assert value['reports']
