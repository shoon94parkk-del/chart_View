from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

import pytest

from guru_rules import evaluate_company
from scripts.generate_guru_screening import ProviderError, refresh_cache
from scripts.merge_guru_cache import merge_cache
from test_guru_rules import company, quote
from test_guru_action_merge import cache, review


def verified_cache():
    row=company()
    row['checkedAt']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    row['corpCode']='00126380'
    return {'companies':{row['symbol']:row},'universe':[{'symbol':row['symbol'],'industry':'제조업'}]}


def test_failed_recollection_survives_workflow_merge_and_blocks_old_candidate():
    before=verified_cache(); untouched=deepcopy(before)
    class FailedProvider:
        requests=0
        def collect(self,*args):
            self.requests+=1
            raise ProviderError('DART network error')
    failed=refresh_cache(before['universe'],before,client=FailedProvider(),
                         max_companies=1,max_requests=5,deadline=time.monotonic()+10)
    merged=merge_cache(before,failed)
    original=before['companies']['005930.KS']; row=merged['companies']['005930.KS']
    assert evaluate_company(original,quote(),strategy='buffett')['status']=='matched'
    assert evaluate_company(row,quote(),strategy='buffett')['status']=='insufficient'
    assert row['refreshError']=='DART network error'
    for field in ('checkedAt','annual','sources','collection','epsComparability'):
        assert row[field]==original[field]
    assert row['lastAttemptAt']==failed['companies']['005930.KS']['lastAttemptAt']
    assert before==untouched


@pytest.mark.parametrize('field,value',[
    ('corpCode','99999999'),('annual',[{'year':2025,'basicEps':9999}]),
    ('sources',{'2025':{'equity':{'filingDate':'2026-03-13'}}}),
])
def test_failed_attempt_cannot_attach_to_different_financial_evidence(field,value):
    before=verified_cache(); failed=deepcopy(before)
    failed['companies']['005930.KS'].update(refreshError='DART network error',lastAttemptAt=datetime.now(timezone.utc).isoformat())
    before['companies']['005930.KS'][field]=value
    assert merge_cache(before,failed)['companies']['005930.KS']==before['companies']['005930.KS']


@pytest.mark.parametrize('attempt,error',[
    ('2020-01-01T00:00:00+00:00','DART network error'),
    ('not-a-date','DART network error'),('2026-10-08T00:00:00','DART network error'),
    ('2026-10-08T23:00:00+09:00',''),('2026-10-08T23:00:00+09:00',None),
])
def test_invalid_or_older_failure_bookkeeping_cannot_change_verified_cache(attempt,error):
    before=verified_cache(); failed=deepcopy(before)
    failed['companies']['005930.KS'].update(refreshError=error,lastAttemptAt=attempt)
    assert merge_cache(before,failed)['companies']['005930.KS']==before['companies']['005930.KS']


def test_newer_success_wins_over_old_failure_and_clears_only_by_new_verification():
    before=verified_cache(); failed=deepcopy(before)
    old=failed['companies']['005930.KS']
    old.update(refreshError='DART network error',lastAttemptAt=datetime.now(timezone.utc).isoformat())
    verified=deepcopy(before)
    verified['companies']['005930.KS']['checkedAt']=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
    assert merge_cache(verified,failed)['companies']['005930.KS']==verified['companies']['005930.KS']
    recovered=merge_cache(failed,verified)['companies']['005930.KS']
    assert 'refreshError' not in recovered
    assert evaluate_company(recovered,quote(),strategy='buffett')['status']=='matched'


def test_action_review_and_failed_financial_attempt_preserve_both_guards():
    before=cache(); action=review(before); failed=deepcopy(before)
    failed['companies']['002460.KS'].update(refreshError='DART network error',lastAttemptAt='2026-10-08T12:00:00+09:00')
    for first,second in ((action,failed),(failed,action)):
        merged=merge_cache(merge_cache(before,first),second)['companies']['002460.KS']
        assert merged['refreshError']=='DART network error'
        assert merged['lastAttemptAt']=='2026-10-08T12:00:00+09:00'
        assert merged['actions']['end']=='2026-10-07'
        assert merged['checkedAt']==before['companies']['002460.KS']['checkedAt']
        assert merged['annual']==before['companies']['002460.KS']['annual']
