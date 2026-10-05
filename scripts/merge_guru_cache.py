"""Keep the newest checked company evidence after concurrent data commits."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from guru_snapshot import atomic_json


def merge_cache(current, collected):
    companies=dict(current.get('companies') or {})
    for symbol,row in (collected.get('companies') or {}).items():
        old=companies.get(symbol)
        if not old or str(row.get('checkedAt',''))>str(old.get('checkedAt','')):
            companies[symbol]=row
    return {**current,**{k:v for k,v in collected.items() if k!='companies'},'companies':companies}


if __name__=='__main__':
    target=ROOT/'static/data/guru_financials.json'
    current=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    collected=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    atomic_json(target,merge_cache(current,collected))
