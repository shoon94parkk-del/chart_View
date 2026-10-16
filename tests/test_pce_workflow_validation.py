"""Execute the real scheduled-workflow validator against optional-source states."""
from copy import deepcopy
import json
from pathlib import Path
import re
import textwrap

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/update-macro-cache.yml'


def validate(payload, tmp_path, monkeypatch):
    workflow = WORKFLOW.read_text(encoding='utf-8')
    section = workflow.split('      - name: Validate inflation and release cache\n', 1)[1]
    match = re.search(r"          python - <<'PY'\n(.*?)\n          PY", section, re.S)
    assert match, 'scheduled inflation validator must remain executable'
    path = tmp_path / 'static' / 'data' / 'inflation_release_cache.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    exec(compile(textwrap.dedent(match[1]), str(WORKFLOW), 'exec'), {})


def cache(*optional):
    rows = []
    for sid in ('cpi', 'core_cpi', 'ppi', 'core_ppi', *optional):
        is_pce = sid in ('pce', 'core_pce')
        rows.append({'id': sid, 'basis': {'yoy': 'SA' if is_pce else 'NSA', 'mom': 'SA'},
                     'sourceIndices': {'sa': []} if is_pce else {'sa': [], 'nsa': []},
                     'points': [{}] * 60, 'asOf': '2026-08',
                     'checkedAt': '2026-10-16T00:00:00Z', 'collectedAt': '2026-10-16T00:00:00Z'})
    return {'inflation': {'series': rows, 'status': 'ok'}, 'releaseCalendar': {'events': [], 'status': 'ok'}}


@pytest.mark.parametrize('optional', [(), ('pce',), ('pce', 'core_pce')])
def test_workflow_accepts_legacy_refresh_when_bea_has_no_first_success(optional, tmp_path, monkeypatch):
    validate(cache(*optional), tmp_path, monkeypatch)


@pytest.mark.parametrize('failure', ['missing_bls', 'unknown_series', 'duplicate_series', 'wrong_pce_basis', 'fake_nsa'])
def test_workflow_still_rejects_missing_required_or_invalid_series(failure, tmp_path, monkeypatch):
    payload = cache('pce', 'core_pce')
    rows = payload['inflation']['series']
    if failure == 'missing_bls':
        rows.pop(0)
    elif failure == 'unknown_series':
        rows.append({**deepcopy(rows[0]), 'id': 'unknown'})
    elif failure == 'duplicate_series':
        rows.append(deepcopy(rows[0]))
    elif failure == 'wrong_pce_basis':
        rows[-1]['basis']['yoy'] = 'NSA'
    elif failure == 'fake_nsa':
        rows[-1]['sourceIndices']['nsa'] = []
    with pytest.raises(AssertionError):
        validate(payload, tmp_path, monkeypatch)
