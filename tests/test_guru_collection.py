import time
from scripts.generate_guru_screening import refresh_cache, DartLimit
from test_guru_financials import report


class FakeClient:
    def __init__(self, limit=False): self.requests=0; self.limit=limit
    def collect(self, row, previous):
        self.requests+=1
        if self.limit: raise DartLimit()
        return {'symbol': row['symbol'], 'collection': {'status': 'complete'}, 'annual': []}


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
    result=refresh_cache([{'symbol':'000001.KS'},{'symbol':'000002.KS'}],{},client=client,max_companies=10,max_requests=10,deadline=time.monotonic()+10)
    assert client.requests==1
    assert result['collection']['status']=='rate_limited'


def test_merge_never_overwrites_newer_checked_evidence():
    from scripts.merge_guru_cache import merge_cache
    current={'companies':{'005930.KS':{'checkedAt':'2026-10-05T18:00:00+09:00','annual':[{'year':2025,'netIncome':19}]}}}
    older={'companies':{'005930.KS':{'checkedAt':'2026-10-05T17:00:00+09:00','annual':[{'year':2025,'netIncome':15}]}}}
    assert merge_cache(current,older)['companies']['005930.KS']['annual'][0]['netIncome']==19
