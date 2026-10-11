"""Publication readiness must follow the displayed version through the evidence API."""
import copy
import hashlib
import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import verify_deployed_release as release

STRATEGIES = ('buffett', 'lynch', 'oneil', 'minervini', 'greenblatt')
EXPECTED_SHA = 'a' * 40


@pytest.fixture
def published(monkeypatch, tmp_path):
    snapshot = {'snapshotVersion': 'a' * 20, 'criteriaVersion': 'cv-gurus-v2',
                'tradeDate': '2026-10-08', 'generatedAt': '2026-10-11T08:11:19+09:00',
                'strategies': {}}
    evidence = {key: snapshot[key] for key in ('snapshotVersion', 'criteriaVersion', 'tradeDate')}
    evidence['companies'] = {}
    for index, strategy in enumerate(STRATEGIES):
        symbol = f'{index + 1:06}.KS'
        snapshot['strategies'][strategy] = {
            'universeCount': 10, 'unsupportedCount': 0, 'pendingCount': 0,
            'insufficientCount': 1, 'failedCount': 8, 'matchedCount': 1,
            'evaluatedCount': 9, 'missingReasons': {'history unavailable': 1},
            'results': [{'symbol': symbol, 'evidenceKey': symbol, 'tradeDate': snapshot['tradeDate']}]}
        evidence['companies'][symbol] = {'symbol': symbol, 'annual': [],
                                         'strategies': {strategy: {'status': 'matched'}}}
    state = {'snapshot': snapshot, 'evidence': evidence, 'remote': copy.deepcopy(snapshot),
             'cdn': copy.deepcopy(snapshot), 'requests': [], 'responses': {}, 'conflict': 409,
             'conflictVersion': snapshot['snapshotVersion'], 'changeOnFinalRead': False}
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    assets, html = {}, ''
    for asset in release.ASSETS:
        path = tmp_path / asset
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(asset.encode())
        url = f'/{asset}?v={hashlib.sha256(path.read_bytes()).hexdigest()[:12]}'
        assets[url] = path.read_bytes()
        html += f'<script src="{url}"></script>'

    def write_local():
        directory = tmp_path / 'static/data'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'guru_screening.json').write_text(json.dumps(snapshot))
        (directory / 'guru_evidence.json').write_text(json.dumps(evidence))

    state['write'] = write_local
    write_local()

    def get(base, path):
        state['requests'].append((base, path))
        if path.startswith('health'):
            return json.dumps({'status': 'ok', 'revision': EXPECTED_SHA}).encode()
        if path.startswith('?'):
            return html.encode()
        if path in assets:
            return assets[path]
        parsed = urlsplit(path)
        if parsed.path.lstrip('/') == 'static/data/guru_screening.json':
            is_cdn = base.startswith('https://raw.githubusercontent.com/')
            result = state['cdn' if is_cdn else 'remote']
            if state['changeOnFinalRead'] and any('/api/guru-investing/' in p for _, p in state['requests']):
                result = dict(result, snapshotVersion='b' * 20)
            return json.dumps(result).encode()
        if parsed.path.startswith('/api/guru-investing/'):
            symbol = parsed.path.rsplit('/', 1)[-1]
            version = parse_qs(parsed.query)['version'][0]
            if version != snapshot['snapshotVersion']:
                body = json.dumps({'detail': {'code': 'snapshot_changed', 'currentVersion': state['conflictVersion']}}).encode()
                if state['conflict'] != 200:
                    raise HTTPError(path, state['conflict'], 'conflict', {}, io.BytesIO(body))
                return body
            row = state['responses'].get(symbol, evidence['companies'][symbol])
            return json.dumps({**row, **{k: evidence[k] for k in ('snapshotVersion', 'criteriaVersion', 'tradeDate')}}).encode()
        raise AssertionError(f'Unexpected release request: {base} {path}')

    monkeypatch.setattr(release, 'get', get)
    return state


def verify():
    return release.verify('https://example.test', EXPECTED_SHA, attempts=1)


def test_release_requires_real_evidence_for_each_of_five_strategies(published):
    result = verify()['guru']
    assert result['snapshotVersion'] == published['snapshot']['snapshotVersion']
    assert set(result['strategies']) == set(STRATEGIES)
    assert all(row['status'] == 'evidence_verified' for row in result['strategies'].values())
    assert result['nonCurrentVersionRejection'] == 'verified_409'


@pytest.mark.parametrize('location', ['remote', 'cdn'])
def test_new_cdn_or_old_backend_cannot_be_publication_ready(published, location):
    published[location]['snapshotVersion'] = 'b' * 20
    with pytest.raises(ValueError, match='Guru snapshot'):
        verify()


@pytest.mark.parametrize('field,value', [('symbol', '999999.KS'), ('strategies', {})])
def test_wrong_company_or_missing_strategy_evidence_blocks_release(published, field, value):
    symbol = published['snapshot']['strategies']['oneil']['results'][0]['symbol']
    published['responses'][symbol] = dict(published['evidence']['companies'][symbol], **{field: value})
    with pytest.raises(ValueError, match='Guru evidence'):
        verify()


def test_local_evidence_from_another_version_blocks_release(published):
    published['evidence']['snapshotVersion'] = 'b' * 20
    published['write']()
    with pytest.raises(ValueError, match='Guru evidence'):
        verify()


def test_missing_local_candidate_evidence_blocks_release(published):
    del published['evidence']['companies']['000003.KS']
    published['write']()
    with pytest.raises(ValueError, match='Guru evidence'):
        verify()


@pytest.mark.parametrize('status', [200, 404, 503])
def test_noncurrent_version_must_be_rejected_with_409(published, status):
    published['conflict'] = status
    with pytest.raises(ValueError, match='Guru non-current'):
        verify()


def test_409_for_a_different_current_version_is_not_ready(published):
    published['conflictVersion'] = 'b' * 20
    with pytest.raises(ValueError, match='Guru non-current'):
        verify()


def test_snapshot_changed_during_verification_blocks_release(published):
    published['changeOnFinalRead'] = True
    with pytest.raises(ValueError, match='Guru snapshot'):
        verify()


@pytest.mark.parametrize('evaluated,expected', [(9, 'no_matches'), (0, 'unavailable')])
def test_empty_or_unavailable_strategy_has_explicit_coverage_not_substitute_evidence(published, evaluated, expected):
    row = published['snapshot']['strategies']['oneil']
    row.update(results=[], matchedCount=0, failedCount=evaluated, evaluatedCount=evaluated,
               insufficientCount=10-evaluated, missingReasons={'history unavailable': 10-evaluated})
    for location in ('remote', 'cdn'):
        published[location] = copy.deepcopy(published['snapshot'])
    published['write']()
    result = verify()['guru']['strategies']['oneil']
    assert result['status'] == expected
    assert result['coverage']['insufficientCount'] == 10-evaluated
    assert result['missingReasons'] == {'history unavailable': 10-evaluated}
    assert not any('/api/guru-investing/000003.KS' in path for _, path in published['requests'])


def test_missing_strategy_cannot_silently_pass_as_empty(published):
    del published['snapshot']['strategies']['oneil']
    published['write']()
    with pytest.raises(ValueError, match='Guru strategies'):
        verify()
