from copy import deepcopy
from test_guru_actions import cache, CHECKED, refresh_action_windows, packets, filing
from scripts.merge_guru_cache import merge_cache


class Client:
    requests=0
    corp_codes={'002460':{'corpCode':'00123456'},'003090':{'corpCode':'00123457'}}
    def __init__(self, rows=()):self.pages=packets(list(rows))
    def get(self,endpoint,params):self.requests+=1;return self.pages[params['page_no']-1]


def review(original, rows=()):
    return refresh_action_windows(original,client=Client(rows),trade_date='2026-10-07',checked_at=CHECKED)


def test_action_only_merge_keeps_financial_checked_time_and_values():
    current=cache();new=review(current);merged=merge_cache(current,new)
    assert merged['companies']['002460.KS']['actions']['end']=='2026-10-07'
    for field in ('checkedAt','annual','reports','sources','collection'):
        assert merged['companies']['002460.KS'][field]==current['companies']['002460.KS'][field]
    assert current==cache()


def test_new_financial_receipt_wins_over_older_action_review():
    current=cache();new=review(current)
    current['companies']['002460.KS']['checkedAt']='2026-10-07T23:16:00+09:00'
    current['companies']['002460.KS']['annual'][0]['basicEps']=9000
    assert merge_cache(current,new)['companies']['002460.KS']==current['companies']['002460.KS']


def test_equal_time_changed_financial_or_mapping_rejects_action_review():
    original=cache();new=review(original)
    for field,value in [('corpCode','99999999'),('annual',[{'year':2025,'basicEps':99}])]:
        current=deepcopy(original);current['companies']['002460.KS'][field]=value
        assert merge_cache(current,new)['companies']['002460.KS']==current['companies']['002460.KS']


def test_newly_found_split_or_financial_filing_stays_unknown_after_merge():
    for name in ['주식분할결정','[기재정정]사업보고서']:
        current=cache();new=review(current,[filing(name=name)])
        assert merge_cache(current,new)['companies']['002460.KS']['epsComparability']['status']=='unknown'


def test_old_review_cannot_replace_newer_scope_or_blocked_company():
    original=cache();older=review(original);current=deepcopy(older)
    current['companies']['002460.KS']['actions']['end']='2026-10-08'
    current['companies']['002460.KS']['actions']['checkedAt']='2026-10-08T23:15:00+09:00'
    current['companies']['002460.KS']['epsComparability']['status']='unknown'
    assert merge_cache(current,older)['companies']['002460.KS']==current['companies']['002460.KS']
