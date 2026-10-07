"""Keep the newest checked company evidence after concurrent data commits."""
import json
from pathlib import Path
import sys
from copy import deepcopy
from datetime import datetime, date

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from guru_snapshot import atomic_json
from guru_actions import renormalize_cached_reports


def _action_patch(old, row):
    # Same financial evidence is mandatory: never attach a review of an older
    # receipt to newly collected/changed annual values, even at an equal time.
    excluded={'actions','epsComparability'}
    if {k:v for k,v in old.items() if k not in excluded}!={k:v for k,v in row.items() if k not in excluded}:
        return None
    actions=row.get('actions') or {}; prior=old.get('actions') or {}
    base=actions.get('reviewBase') or {}; eps=row.get('epsComparability') or {}
    try:
        checked=datetime.fromisoformat(actions['checkedAt'])
        previous_checked=datetime.fromisoformat(prior.get('checkedAt') or old['checkedAt'])
        if checked.tzinfo is None or previous_checked.tzinfo is None or checked<=previous_checked:return None
        if date.fromisoformat(actions['end'])<=date.fromisoformat(prior['end']):return None
    except (KeyError,ValueError,TypeError):return None
    if (base.get('financialCheckedAt')!=old.get('checkedAt') or base.get('corpCode')!=old.get('corpCode') or
        base.get('previousEnd')!=prior.get('end') or prior.get('status')!='verified' or prior.get('events') or
        (old.get('epsComparability') or {}).get('status')!='verified' or
        actions.get('start')!=prior.get('start') or actions.get('source')!=prior.get('source') or
        eps.get('start')!=actions.get('start') or eps.get('end')!=actions.get('end') or eps.get('source')!=actions.get('source')):
        return None
    return {**old,'actions':deepcopy(actions),'epsComparability':deepcopy(eps)}


def merge_cache(current, collected):
    current=renormalize_cached_reports(current);collected=renormalize_cached_reports(collected)
    companies=dict(current.get('companies') or {})
    for symbol,row in (collected.get('companies') or {}).items():
        old=companies.get(symbol)
        if not old or str(row.get('checkedAt',''))>str(old.get('checkedAt','')):
            companies[symbol]=row
        elif row.get('checkedAt')==old.get('checkedAt'):
            patch=_action_patch(old,row)
            if patch:companies[symbol]=patch
    metadata = collected if str(collected.get('generatedAt','')) >= str(current.get('generatedAt','')) else current
    result={**metadata,'companies':companies}
    reviews=[value.get('actionCollection') for value in (current,collected) if value.get('actionCollection')]
    if reviews:result['actionCollection']=max(reviews,key=lambda value:str(value.get('checkedAt','')))
    return result


if __name__=='__main__':
    target=ROOT/'static/data/guru_financials.json'
    current=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    collected=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    atomic_json(target,merge_cache(current,collected))
