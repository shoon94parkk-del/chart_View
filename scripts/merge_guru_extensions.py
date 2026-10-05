"""Merge provider checkpoints without overwriting a newer observation."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from guru_snapshot import atomic_json


def merge(current,collected,kind):
    companies=dict(current.get('companies') or {})
    for s,row in (collected.get('companies') or {}).items():
        old=companies.get(s) or {}
        fields=('tradeDate',) if kind=='market' else ('year','quarter','checkedAt')
        if not old or tuple(row.get(k,'') for k in fields)>=tuple(old.get(k,'') for k in fields): companies[s]=row
    meta=collected if collected.get('generatedAt','')>=current.get('generatedAt','') else current
    return {**meta,'companies':companies}


if __name__=='__main__':
    for kind,source in zip(('market','quarters'),sys.argv[1:]):
        source=Path(source);target=ROOT/'static/data'/f'guru_{kind}.json'
        if not source.exists(): continue
        current=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        atomic_json(target,merge(current,json.loads(source.read_text(encoding='utf-8')),kind))
