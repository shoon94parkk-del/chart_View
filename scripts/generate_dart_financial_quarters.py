"""Daily checked-in quarter cache for the same established DART company set."""
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dart_quarter_service import _collect, STATIC_PATH

def main():
    history=json.loads(Path('static/data/dart_financial_history.json').read_text(encoding='utf-8'))
    old=json.loads(STATIC_PATH.read_text(encoding='utf-8')) if STATIC_PATH.exists() else {'companies':{}}
    companies=dict(old.get('companies') or {})
    codes=list((history.get('companies') or {}).keys())
    def collect(code):
        row=_collect(code,f'{code}.KS')
        return code,row
    with ThreadPoolExecutor(max_workers=2) as pool:
        for code,row in pool.map(collect,codes):
            if row.get('available'):
                row.pop('checkedAt',None)  # Commit only when the underlying filing data changes.
                companies[code]=row
            print(code,'ready' if row.get('available') else row.get('reason','unavailable'))
    if not companies:raise RuntimeError('No validated quarterly reports; preserve existing cache')
    STATIC_PATH.write_text(json.dumps({'schemaVersion':1,'companies':companies},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Validated quarterly histories:',len(companies))

if __name__=='__main__':main()
