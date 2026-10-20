"""Merge reviewed PUBLIC projections only. Never reads private source records.

All inputs are validated before any output changes. Writes are atomic per
independent feed. CI serializes publishers; git push remains fast-forward only.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from debate_archive_service import MAX_BYTES, public_archive, public_shadow_status

ARCHIVE = 'intelligence_debates_public.json'
SHADOW = 'intelligence_shadow_status.json'


def read_json(path: Path, limit: int = MAX_BYTES):
    with path.open('rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('public projection too large')
    return json.loads(content)


def instant(value: str):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def merge_archive(existing, incoming):
    incoming = public_archive(incoming)
    current = public_archive(existing) if existing else None
    rows = {row['id']: row for row in current['debates']} if current else {}
    changed = False
    for row in incoming['debates']:
        # All new automatic publications use the completion and metadata gate.
        if 'summary' not in row or 'updated_at' not in row:
            raise ValueError('new publications require summary and updated_at')
        for phase in row['phases']:
            source = phase['source_path']
            if len(source) >= 260 or '..' in source or not re.fullmatch(r'records/(?:debates|shadow)/[A-Za-z0-9_./-]+\.md', source):
                raise ValueError('source path is incompatible with the public viewer')
        previous = rows.get(row['id'])
        if previous == row:
            continue
        if previous:
            old_time = previous.get('updated_at', previous['date'] + 'T00:00:00Z')
            if instant(row['updated_at']) <= instant(old_time):
                raise ValueError('older or conflicting report revision')
        rows[row['id']] = row
        changed = True
    if not changed:
        return current
    generated = max([datetime.now(timezone.utc), instant(incoming['generated_at'])] +
                    ([instant(current['generated_at'])+timedelta(milliseconds=1)] if current else []))
    return public_archive({
        'schema_version': 1, 'kind': 'debate_archive',
        'publication_status': 'EXPLICITLY_APPROVED', 'generated_at': generated.isoformat(),
        'debates': sorted(rows.values(), key=lambda row: (row['date'], row.get('updated_at',''), row['id']), reverse=True),
    })


def atomic_json(path: Path, document):
    raw = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    limit = MAX_BYTES if path.name == ARCHIVE else 16384
    if len(raw) > limit:
        raise ValueError('merged public projection too large')
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def publish(*, archive=None, shadow=None, output_dir=Path('static/data'), check=False):
    if archive is None and shadow is None:
        raise ValueError('no public projection supplied')
    output_dir = Path(output_dir)
    writes = []
    if archive is not None:
        target = output_dir / ARCHIVE
        existing = read_json(target) if target.exists() else None
        merged = merge_archive(existing, archive)
        if merged != existing:
            writes.append((target, merged))
    if shadow is not None:
        clean = public_shadow_status(shadow)
        target = output_dir / SHADOW
        existing = public_shadow_status(read_json(target, 16384)) if target.exists() else None
        if existing and instant(clean['generated_at']) < instant(existing['generated_at']):
            raise ValueError('older Shadow publication')
        if existing and instant(clean['generated_at']) == instant(existing['generated_at']) and clean != existing:
            raise ValueError('conflicting Shadow publication')
        if clean != existing:
            writes.append((target, clean))
    # Preflight both byte budgets before replacing either independent feed.
    for target, doc in writes:
        limit = MAX_BYTES if target.name == ARCHIVE else 16384
        if len((json.dumps(doc, ensure_ascii=False, indent=2)+'\n').encode()) > limit:
            raise ValueError('merged public projection too large')
    if not check:
        for target, doc in writes:
            atomic_json(target, doc)
    return [target.name for target, _ in writes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--shadow', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1]/'static/data')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        names = publish(archive=read_json(args.archive) if args.archive else None,
                        shadow=read_json(args.shadow, 16384) if args.shadow else None,
                        output_dir=args.output_dir, check=args.check)
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(1, 'Public projection rejected; existing publications preserved.\n')
    print(('Validated: ' if args.check else 'Published: ') + (', '.join(names) or 'unchanged'))


if __name__ == '__main__':
    main()
