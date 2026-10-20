"""Public, reviewed research reaches consumers without frontend redeploys."""
import copy
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import published_data
import test_debate_archive_service as archive_fixtures
from test_published_data import _Response


def sample():
    return archive_fixtures.TestDebateArchive().extended()


def publisher():
    from scripts.publish_debate_archive import publish
    return publish


def test_atomic_merge_preserves_other_reports_and_is_idempotent(tmp_path):
    publish = publisher()
    first = sample()
    publish(archive=first, output_dir=tmp_path)
    target = tmp_path / 'intelligence_debates_public.json'
    before = target.read_bytes()
    assert publish(archive=first, output_dir=tmp_path) == []
    assert target.read_bytes() == before
    second = sample()
    second['debates'][0]['id'] = 'second-report'
    publish(archive=second, output_dir=tmp_path)
    assert len(json.loads(target.read_bytes())['debates']) == 2
    assert not list(tmp_path.glob('*.tmp'))


def test_invalid_private_incomplete_or_older_input_leaves_last_good_bytes(tmp_path):
    publish = publisher()
    original = sample()
    publish(archive=original, output_dir=tmp_path)
    target = tmp_path / 'intelligence_debates_public.json'
    before = target.read_bytes()
    for change in ('private', 'incomplete', 'old', 'legacy'):
        doc = copy.deepcopy(original)
        row = doc['debates'][0]
        if change == 'private': row['summary'] = '현재 보유 300주'
        if change == 'incomplete': row['phases'] = row['phases'][:2]
        if change == 'old': row['updated_at'] = '2026-10-13T00:00:00Z'
        if change == 'legacy': del row['summary']; del row['updated_at']
        with pytest.raises(ValueError): publish(archive=doc, output_dir=tmp_path)
        assert target.read_bytes() == before


def test_publication_cap_rejects_instead_of_losing_history(tmp_path):
    publish = publisher()
    doc = sample()
    doc['debates'] = [dict(doc['debates'][0], id=f'report-{i}') for i in range(30)]
    publish(archive=doc, output_dir=tmp_path)
    new = sample(); new['debates'][0]['id'] = 'new-report'
    with pytest.raises(ValueError): publish(archive=new, output_dir=tmp_path)
    assert len(json.loads((tmp_path / 'intelligence_debates_public.json').read_bytes())['debates']) == 30


def test_skewed_publisher_clock_cannot_reuse_a_publication_revision(tmp_path):
    from scripts.publish_debate_archive import publish
    doc = sample()
    future = (datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()
    doc['generated_at'] = doc['debates'][0]['updated_at'] = future
    publish(archive=doc, output_dir=tmp_path)
    target = tmp_path / 'intelligence_debates_public.json'
    previous = json.loads(target.read_bytes())['generated_at']
    doc['debates'][0]['id'] = 'another-report'
    publish(archive=doc, output_dir=tmp_path)
    assert datetime.fromisoformat(json.loads(target.read_bytes())['generated_at']) > datetime.fromisoformat(previous)


def test_research_reader_validates_new_publications_and_keeps_newest_remote(tmp_path):
    old = sample()
    old['generated_at'] = old['debates'][0]['updated_at'] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    new = sample()
    new['debates'][0]['summary'] = '새 최종 평가'
    filename = 'intelligence_debates_public.json'
    (tmp_path / filename).write_text(json.dumps(old), encoding='utf-8')
    with patch.object(published_data, '_DATA_DIR', tmp_path), patch.object(published_data, '_CACHE', {}):
        with patch.object(published_data, 'urlopen', return_value=_Response(json.dumps(new).encode())):
            result, source = published_data.get_published_data(filename)
        assert source == 'github-main'
        assert result['debates'][0]['summary'] == '새 최종 평가'
        for response in (old, {**new, 'publication_status':'DRAFT'}):
            published_data._CACHE[filename] = (0, result, source)
            with patch.object(published_data, 'urlopen', return_value=_Response(json.dumps(response).encode())):
                result, source = published_data.get_published_data(filename)
            assert result['debates'][0]['summary'] == '새 최종 평가'
            assert source == 'cached-published-fallback'


def test_real_instants_compare_correctly_across_timezone_offsets(tmp_path):
    old = sample(); new = sample()
    old['generated_at'] = old['debates'][0]['updated_at'] = '2026-10-13T09:00:00+09:00'
    new['generated_at'] = new['debates'][0]['updated_at'] = '2026-10-13T01:00:00Z'
    new['debates'][0]['summary'] = '실제로 한 시간 뒤'
    filename = 'intelligence_debates_public.json'
    (tmp_path / filename).write_text(json.dumps(old), encoding='utf-8')
    with patch.object(published_data, '_DATA_DIR', tmp_path), patch.object(published_data, '_CACHE', {}):
        with patch.object(published_data, 'urlopen', return_value=_Response(json.dumps(new).encode())):
            result, _ = published_data.get_published_data(filename)
    assert result['debates'][0]['summary'] == '실제로 한 시간 뒤'
