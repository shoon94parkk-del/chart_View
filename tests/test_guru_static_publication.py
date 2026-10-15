import copy
import json
import pytest
from guru_snapshot import build_snapshot, publish_snapshot
from test_guru_snapshot import inputs


def test_each_candidate_has_small_same_version_static_evidence(tmp_path):
    snapshot,evidence=build_snapshot(*inputs(),generated_at='2026-10-05T17:00:00+09:00')
    publish_snapshot(snapshot,evidence,tmp_path)
    for symbol,company in evidence['companies'].items():
        file=tmp_path/'guru_evidence'/snapshot['snapshotVersion']/(symbol+'.json')
        actual=json.loads(file.read_text())
        assert actual=={**company,**{k:evidence[k] for k in ['snapshotVersion','criteriaVersion','tradeDate']}}
        assert len(actual['strategies'])>0


def test_previous_open_list_keeps_its_immutable_evidence(tmp_path):
    args=inputs();first,evidence=build_snapshot(*args,generated_at='2026-10-05T17:00:00+09:00')
    publish_snapshot(first,evidence,tmp_path)
    file=tmp_path/'guru_evidence'/first['snapshotVersion']/'005930.KS.json'
    original=file.read_bytes()
    args[2]['companies']['005930.KS']['annual'][-1]['netIncome']*=1.1
    second,second_evidence=build_snapshot(*args,generated_at='2026-10-06T17:00:00+09:00')
    assert first['snapshotVersion']!=second['snapshotVersion']
    publish_snapshot(second,second_evidence,tmp_path)
    assert file.read_bytes()==original


def test_unsafe_version_cannot_escape_static_publication_root(tmp_path):
    snapshot,evidence=build_snapshot(*inputs(),generated_at='2026-10-05T17:00:00+09:00')
    snapshot['snapshotVersion']=evidence['snapshotVersion']='../escaped'
    with pytest.raises(ValueError):publish_snapshot(snapshot,evidence,tmp_path)
    assert not (tmp_path/'guru_screening.json').exists()


def test_republishing_unchanged_current_version_keeps_previous_proof(tmp_path):
    args=inputs();first,evidence=build_snapshot(*args,generated_at='2026-10-05T17:00:00+09:00')
    publish_snapshot(first,evidence,tmp_path)
    old=tmp_path/'guru_evidence'/first['snapshotVersion']/'005930.KS.json'
    args[2]['companies']['005930.KS']['annual'][-1]['netIncome']*=1.1
    second,proof=build_snapshot(*args,generated_at='2026-10-06T17:00:00+09:00')
    publish_snapshot(second,proof,tmp_path)
    publish_snapshot(second,proof,tmp_path)
    assert old.exists()


def test_empty_snapshot_can_be_staged_by_the_publication_workflow(tmp_path):
    import subprocess
    universe,prices,financials=inputs()
    snapshot,evidence=build_snapshot([],prices,financials,generated_at='2026-10-05T17:00:00+09:00')
    publish_snapshot(snapshot,evidence,tmp_path/'static/data')
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    staged=subprocess.run(['git','add','-A','static/data/guru_evidence/'],cwd=tmp_path,capture_output=True,text=True)
    assert staged.returncode==0,staged.stderr
    assert all(not row['results'] for row in snapshot['strategies'].values())
