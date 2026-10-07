from copy import deepcopy
import pytest

from guru_actions import refresh_action_windows, renormalize_cached_reports
from guru_financials import normalize_reports

SOURCE = 'OpenDART disclosures: split/reverse split/stock dividend/bonus issue'
CHECKED = '2026-10-07T23:15:00+09:00'


def company(symbol='002460.KS', corp='00123456'):
    return {'symbol': symbol, 'corpCode': corp, 'checkedAt': '2026-10-05T18:00:00+09:00',
            'classification': {'status': 'supported'}, 'annual': [{'year': 2025, 'basicEps': 2916}],
            'sources': {'2025': {'basicEps': {'receiptNo': '20260319000781'}}},
            'reports': [{'unmodified': True}], 'collection': {'status': 'complete'},
            'actions': {'status': 'verified', 'source': SOURCE, 'start': '2022-01-01', 'end': '2026-10-05', 'events': []},
            'epsComparability': {'status': 'verified', 'source': SOURCE, 'start': '2022-01-01', 'end': '2026-10-05', 'events': []}}


def cache():
    rows = [company(), company('003090.KS', '00123457')]
    return {'companies': {r['symbol']: r for r in rows},
            'universe': [{'symbol': r['symbol']} for r in rows],
            'generatedAt': '2026-10-05T18:00:00+09:00', 'collection': {'status': 'complete'}}


def filing(index=1, corp='00123456', name='주요사항보고서(자기주식취득결정)', observed='20261006'):
    return {'corp_code': corp, 'rcept_no': observed + f'{index:06d}', 'rcept_dt': observed, 'report_nm': name}


def packets(rows):
    total = len(rows)
    return [{'status': '000', 'page_no': i + 1, 'page_count': 100,
             'total_count': total, 'total_page': (total + 99) // 100,
             'list': rows[i * 100:(i + 1) * 100]} for i in range((total + 99) // 100)] or [{'status': '013'}]


class Client:
    def __init__(self, responses):
        self.responses = deepcopy(responses)
        self.requests = 0
        self.calls = []
        self.corp_codes = {'002460': {'corpCode': '00123456'}, '003090': {'corpCode': '00123457'}}

    def get(self, endpoint, params):
        self.requests += 1
        self.calls.append((endpoint, params))
        response = self.responses[self.requests - 1]
        if isinstance(response, Exception):
            raise response
        return response


def refresh(data, client, **options):
    return refresh_action_windows(data, client=client, trade_date='2026-10-07', checked_at=CHECKED, **options)


@pytest.mark.parametrize('responses', [[{'status': '013'}], packets([filing()])])
def test_full_official_review_advances_only_scope_and_preserves_financial_evidence(responses):
    before = cache()
    untouched = deepcopy(before)
    client = Client(responses)
    result = refresh(before, client)
    assert before == untouched
    assert result['collection'] == before['collection']
    assert result['generatedAt'] == before['generatedAt']
    assert result['actionCollection']['status'] == 'complete'
    assert result['actionCollection']['updatedCount'] == 2
    for symbol, original in before['companies'].items():
        row = result['companies'][symbol]
        for key in ('checkedAt', 'annual', 'sources', 'reports', 'collection', 'corpCode', 'classification'):
            assert row[key] == original[key]
        assert row['actions']['end'] == row['epsComparability']['end'] == '2026-10-07'
        assert row['epsComparability']['status'] == 'verified'
        assert row['actions']['checkedAt'] == CHECKED
        assert row['actions']['reviewBase']['financialCheckedAt'] == original['checkedAt']
    assert client.calls[0] == ('list.json', {'bgn_de': '20261006', 'end_de': '20261007',
                                          'page_count': 100, 'page_no': 1, 'sort': 'date', 'sort_mth': 'asc'})


@pytest.mark.parametrize('mutation', ['unknown', 'events', 'corp', 'scope', 'date', 'identity', 'start', 'unsupported'])
def test_unverified_or_mismatched_company_cannot_be_certified(mutation):
    before = cache()
    row = before['companies']['002460.KS']
    if mutation == 'unknown': row['epsComparability']['status'] = 'unknown'
    if mutation == 'events': row['actions']['events'] = [{'date': '20230101', 'name': '주식분할결정'}]
    if mutation == 'corp': row['corpCode'] = '99999999'
    if mutation == 'scope': row['epsComparability']['end'] = '2026-10-04'
    if mutation == 'date': row['actions']['end'] = row['epsComparability']['end'] = '2026-10-08'
    if mutation == 'identity': row['symbol'] = '003090.KS'
    if mutation == 'start': row['actions']['start'] = row['epsComparability']['start'] = '2026-10-06'
    if mutation == 'unsupported': row['classification']['status'] = 'unsupported'
    assert refresh(before, Client([{'status': '013'}]))['companies']['002460.KS'] == row


def test_last_page_corporate_action_blocks_only_the_exact_company():
    rows = [filing(i, corp='99999999') for i in range(1, 101)] + [filing(101, name='주식분할결정')]
    result = refresh(cache(), Client(packets(rows)))
    affected = result['companies']['002460.KS']
    assert affected['epsComparability']['status'] == 'unknown'
    assert affected['actions']['events'][0]['receiptNo'] == '20261006000101'
    assert affected['annual'][0]['basicEps'] == 2916
    assert result['companies']['003090.KS']['epsComparability']['status'] == 'verified'
    assert result['actionCollection']['blockedCount'] == 1


@pytest.mark.parametrize('name', ['사업보고서 (2025.12)', '[기재정정]사업보고서 (2025.12)', '[첨부정정]반기보고서', '분기보고서'])
def test_new_financial_filing_requires_financial_reverification_without_rewriting_eps(name):
    before = cache()
    result = refresh(before, Client(packets([filing(name=name)])))
    row = result['companies']['002460.KS']
    assert row['epsComparability']['status'] == 'unknown'
    assert row['epsComparability']['reason'] == '새 재무공시 재확인 필요'
    assert row['actions']['financialRefreshRequired'][0]['name'] == name
    assert row['annual'] == before['companies']['002460.KS']['annual']
    assert row['sources'] == before['companies']['002460.KS']['sources']
    assert result['companies']['003090.KS']['epsComparability']['status'] == 'verified'


@pytest.mark.parametrize('failure', ['020', 'timeout', 'budget', 'partial013', 'wrongpage', 'count', 'identity', 'date', 'duplicate', 'changingtotal'])
def test_any_partial_or_invalid_scan_rolls_back_the_entire_company_batch(failure):
    before = cache()
    responses = packets([filing(i) for i in range(1, 102)])
    if failure == '020': responses[1] = {'status': '020'}
    if failure == 'timeout': responses[1] = TimeoutError('https://provider?crtfc_key=must-not-leak')
    if failure == 'budget': responses[1] = RuntimeError('budget exceeded')
    if failure == 'partial013': responses[1] = {'status': '013'}
    if failure == 'wrongpage': responses[1]['page_no'] = 1
    if failure == 'count': responses[1]['list'] = []
    if failure == 'identity': responses[1]['list'][0]['corp_code'] = ''
    if failure == 'date': responses[1]['list'][0]['rcept_dt'] = '20261008'
    if failure == 'duplicate': responses[1]['list'][0] = responses[0]['list'][0]
    if failure == 'changingtotal': responses[1]['total_count'] = 102
    result = refresh(before, Client(responses))
    assert result['companies'] == before['companies']
    assert result['actionCollection']['status'] == ('provider_error' if failure == 'timeout' else 'unavailable')
    assert result['actionCollection']['updatedCount'] == 0
    assert 'must-not-leak' not in str(result['actionCollection'])


def test_page_or_short_window_budget_never_advances_a_partial_review():
    before = cache()
    client = Client(packets([filing(i) for i in range(1, 102)]))
    result = refresh(before, client, max_pages=1)
    assert result['companies'] == before['companies']
    assert result['actionCollection']['status'] == 'unavailable'
    assert client.requests == 1
    for row in before['companies'].values():
        row['actions']['end'] = row['epsComparability']['end'] = '2026-08-01'
    client = Client([])
    assert refresh(before, client)['companies'] == before['companies']
    assert client.requests == 0


def test_no_provider_call_when_all_companies_are_already_reviewed():
    before = cache()
    for row in before['companies'].values():
        row['actions']['end'] = row['epsComparability']['end'] = '2026-10-07'
    client = Client([])
    result = refresh(before, client)
    assert result['companies'] == before['companies']
    assert client.requests == 0


def reports():
    values = []
    for year, receipt in [(2023, '20240319000781'), (2025, '20260319000781')]:
        values.append({'year': year, 'basis': 'CFS', 'periodEnd': f'{year}-12-31',
            'periods': {name: {'start': f'{year-i}-01-01', 'end': f'{year-i}-12-31'} for i,name in enumerate(('thstrm', 'frmtrm', 'bfefrmtrm'))},
            'receiptNo': receipt, 'filingDate': f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}',
            'rows': [{'sj_div': 'IS', 'account_id': 'ifrs-full_BasicEarningsLossPerShare',
                'account_nm': '기본 및 희석주당이익', 'account_detail': '-', 'currency': 'KRW', 'rcept_no': receipt,
                'thstrm_amount': '2916', 'frmtrm_amount': '1000', 'bfefrmtrm_amount': '500'}]})
    return values


def test_cached_eps_reparse_uses_only_retained_official_sources_without_false_freshness():
    raw = reports()
    row = company()
    normalized = normalize_reports(raw, symbol=row['symbol'], classification=row['classification'], actions=row['actions'])
    row.update(normalized, reports=raw)
    for annual in row['annual']:
        annual['basicEps'] = None
        row['sources'][str(annual['year'])]['basicEps']['accountId'] = None
        row['sources'][str(annual['year'])]['basicEps']['accountName'] = None
    row['epsComparability']['status'] = 'unknown'
    row['epsComparability']['reason'] = 'original unresolved history'
    before = {'companies': {row['symbol']: row}, 'universe': [{'symbol': row['symbol']}], 'collection': {'status': 'complete'}}
    untouched = deepcopy(before)
    result = renormalize_cached_reports(before)
    assert before == untouched
    after = result['companies'][row['symbol']]
    assert after['annual'][-1]['basicEps'] == 2916
    assert after['sources']['2025']['basicEps']['accountId'] == 'ifrs-full_BasicEarningsLossPerShare'
    for key in ('checkedAt', 'reports', 'collection', 'epsComparability', 'actions', 'symbol', 'corpCode'):
        assert after[key] == row[key]
    assert result['collection'] == before['collection']
    assert result['epsNormalization']['updatedCompanies'] == 1
    for old, new in zip(row['annual'], after['annual']):
        assert {k:v for k,v in new.items() if k != 'basicEps'} == {k:v for k,v in old.items() if k != 'basicEps'}


def test_reparse_never_changes_mismatched_basis_or_period_inventory():
    row = company()
    row.update(reports=reports(), basis='OFS', annualReportYear=2025)
    before = {'companies': {row['symbol']: row}}
    assert renormalize_cached_reports(before)['companies'] == before['companies']


@pytest.mark.parametrize('name,status,reason', [
    ('DartLimit','rate_limited','dart_rate_limit'),
    ('BudgetLimit','budget_exhausted','review_budget_exhausted'),
    ('ProviderError','provider_error','provider_request_failed'),
    ('TimeoutError','provider_error','provider_timeout'),
    ('ValueError','unavailable','unexpected_review_error'),
])
def test_provider_diagnostics_use_only_known_class_and_enum_never_messages(name, status, reason):
    error = type(name, (Exception,), {})('https://provider?crtfc_key=must-not-leak')
    before = cache()
    result = refresh(before, Client([error]))
    assert result['companies'] == before['companies']
    metadata = result['actionCollection']
    assert metadata['status'] == status
    assert metadata['reason'] == reason
    assert metadata['diagnostics']['stage'] == 'request'
    assert metadata['diagnostics']['exceptionType'] == (name if name != 'ValueError' else 'UnexpectedError')
    assert 'must-not-leak' not in str(metadata)
    assert 'https:' not in str(metadata)


def test_invalid_pagination_reports_bounded_shape_without_response_body_or_values():
    response = packets([filing()])[0]
    response['page_count'] = 'crtfc_key=must-not-leak'
    response['message'] = 'https://provider?crtfc_key=must-not-leak'
    result = refresh(cache(), Client([response]))
    metadata = result['actionCollection']
    assert metadata['reason'] == 'invalid_pagination'
    assert metadata['diagnostics'] == {'stage':'pagination','requestedPage':1,'responseStatus':'000',
        'pageNo':1,'pageCount':None,'totalCount':1,'totalPages':1,'rowCount':1,'missingFields':[]}
    assert 'must-not-leak' not in str(metadata)


@pytest.mark.parametrize('field', ['corp_code','rcept_no','rcept_dt','report_nm'])
def test_invalid_filing_identifies_only_the_field_without_sensitive_value(field):
    response = packets([filing()])[0]
    response['list'][0][field] = ''
    result = refresh(cache(), Client([response]))
    assert result['companies'] == cache()['companies']
    assert result['actionCollection']['reason'] == 'invalid_filing_identity'
    assert result['actionCollection']['diagnostics']['invalidFields'] == [field]


def test_official_receipt_identifier_prefix_does_not_override_reception_date():
    response = packets([filing()])[0]
    response['list'][0]['rcept_no'] = '20261005000001'
    before = cache()
    result = refresh(before, Client([response]))
    metadata = result['actionCollection']
    assert metadata['status'] == 'complete'
    assert metadata['reason'] is None
    assert metadata['updatedCount'] == 2
    assert metadata['diagnostics']['dateWithinWindow'] is True
    assert metadata['diagnostics']['receiptDateMatches'] is False
    for symbol, row in result['companies'].items():
        assert row['epsComparability']['status'] == 'verified'
        assert row['epsComparability']['end'] == '2026-10-07'
        for field in ('checkedAt','annual','sources','reports'):
            assert row[field] == before['companies'][symbol][field]


def test_last_page_split_with_unrelated_receipt_prefix_uses_actual_reception_date():
    rows = [filing(i, corp='99999999') for i in range(1, 101)]
    split = filing(101, name='주식분할결정')
    split['rcept_no'] = '20261005000101'
    rows.append(split)
    before = cache()
    result = refresh(before, Client(packets(rows)))
    assert result['actionCollection']['status'] == 'complete'
    assert result['actionCollection']['blockedCount'] == 1
    affected = result['companies']['002460.KS']
    assert affected['epsComparability']['status'] == 'unknown'
    assert affected['actions']['events'] == [{'date':'20261006','name':'주식분할결정','receiptNo':'20261005000101'}]
    assert affected['annual'] == before['companies']['002460.KS']['annual']
    assert result['companies']['003090.KS']['epsComparability']['status'] == 'verified'


@pytest.mark.parametrize('observed', ['20261008','20261005','20260230'])
def test_receipt_identifier_cannot_make_outside_or_invalid_actual_date_valid(observed):
    response = packets([filing()])[0]
    response['list'][0].update(rcept_no='20261006000001', rcept_dt=observed)
    before = cache()
    result = refresh(before, Client([response]))
    assert result['companies'] == before['companies']
    assert result['actionCollection']['status'] == 'unavailable'
    assert result['actionCollection']['reason'] in {'invalid_date','invalid_filing_date'}


def test_non_mapping_response_is_an_explicit_safe_shape_error():
    result = refresh(cache(), Client(['https://provider?crtfc_key=must-not-leak']))
    assert result['actionCollection']['reason'] == 'invalid_response_shape'
    assert result['companies'] == cache()['companies']
    assert 'must-not-leak' not in str(result['actionCollection'])
