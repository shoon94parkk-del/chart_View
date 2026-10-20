"""Validate reviewed PUBLIC JSON, then dispatch the trusted main publisher.

Uses the caller's existing gh authentication. Never reads tokens or private
records. The 60KB dispatch limit is intentionally below GitHub's input budget.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.publish_debate_archive import read_json, merge_archive
from debate_archive_service import public_shadow_status


def dispatch(*, archive=None, shadow=None, check=False):
    inputs = {}
    if archive:
        doc = read_json(Path(archive))
        merge_archive(None, doc)  # extension/completion gate, not just JSON parsing
        inputs['archive_json'] = json.dumps(doc, ensure_ascii=False)
    if shadow:
        doc = public_shadow_status(read_json(Path(shadow), 16384))
        inputs['shadow_json'] = json.dumps(doc, ensure_ascii=False)
    if not inputs:
        raise ValueError('no approved public input')
    raw = json.dumps(inputs, ensure_ascii=False)
    if len(raw.encode('utf-8')) > 60000:
        raise ValueError('dispatch exceeds 60KB; use reviewed git publication instead')
    if not check:
        subprocess.run(['gh','workflow','run','publish-intelligence.yml','--repo',
                        'shoon94parkk-del/chart_View','--ref','main','--json'],
                       input=raw, text=True, check=True)
    return len(raw.encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--shadow', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        size = dispatch(archive=args.archive, shadow=args.shadow, check=args.check)
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
        parser.exit(1, 'Public publication dispatch rejected or failed. Existing publications preserved.\n')
    print(('Validated' if args.check else 'Dispatched') + f' public projection ({size} bytes).')


if __name__ == '__main__':
    main()
