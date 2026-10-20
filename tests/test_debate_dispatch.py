import json
from pathlib import Path
from unittest.mock import patch

import pytest
from test_debate_publication import sample


def test_dispatch_validates_before_gh_and_passes_json_stdin_without_shell(tmp_path):
    from scripts.dispatch_debate_publication import dispatch
    source = tmp_path / 'public.json'
    doc = sample()
    source.write_text(json.dumps(doc), encoding='utf-8')
    with patch('scripts.dispatch_debate_publication.subprocess.run') as run:
        dispatch(archive=source)
    args, kwargs = run.call_args
    assert args[0] == ['gh','workflow','run','publish-intelligence.yml','--repo','shoon94parkk-del/chart_View','--ref','main','--json']
    assert json.loads(json.loads(kwargs['input'])['archive_json'])['debates'][0]['summary'] == doc['debates'][0]['summary']
    assert kwargs.get('shell', False) is False
    assert kwargs['encoding'] == 'utf-8'


def test_dispatch_rejects_private_and_oversized_payloads_without_launching_gh(tmp_path):
    from scripts.dispatch_debate_publication import dispatch
    source = tmp_path / 'public.json'
    for private in (True, False):
        doc = sample()
        if private:
            doc['debates'][0]['topic'] = '본인 계좌 잔액'
        else:
            for phase in doc['debates'][0]['phases']:
                phase['text'] = '공개 리서치 '*2000
        source.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        with patch('scripts.dispatch_debate_publication.subprocess.run') as run:
            with pytest.raises(ValueError): dispatch(archive=source)
            run.assert_not_called()


def test_archive_invalid_shadow_cannot_partially_publish(tmp_path):
    from scripts.publish_debate_archive import publish
    with pytest.raises(ValueError): publish(archive=sample(), shadow={'state':'RUNNING'}, output_dir=tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_workflow_uses_trusted_main_and_never_interpolates_public_text_as_code():
    workflow = Path('.github/workflows/publish-intelligence.yml').read_text()
    assert 'ref: main' in workflow
    assert 'cancel-in-progress: false' in workflow
    assert 'queue: max' in workflow
    assert '${{ inputs.' not in workflow and '${{ github.event.client_payload' not in workflow
    assert 'git push origin HEAD:main' in workflow
    assert '--force' not in workflow
