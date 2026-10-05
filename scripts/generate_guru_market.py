"""Bounded, dated OHLCV cache. Never change the existing technical screener."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from guru_snapshot import atomic_json
from guru_extensions import technical_metrics
from guru_financials import classify_company
from scripts.generate_screener import extract_frame, KST


def frame_bars(frame,trade_date):
    if frame is None or frame.empty or any(k not in frame for k in ('Close','High','Low','Volume')): return None
    rows=[]
    for dt,r in frame.iterrows():
        day=dt.date().isoformat()
        if day>trade_date: continue
        vals=[r[k] for k in ('Close','High','Low','Volume')]
        if any(pd.isna(v) for v in vals): return None
        rows.append([day,*[float(v) for v in vals]])
    rows=rows[-273:]
    return rows if technical_metrics(rows,trade_date) else None


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--max-seconds',type=int,default=240);parser.add_argument('--only-missing',action='store_true');args=parser.parse_args()
    out=ROOT/'static/data'; financials=json.loads((out/'guru_financials.json').read_text(encoding='utf-8'))
    prices=json.loads((out/'screener.json').read_text(encoding='utf-8')); trade=prices['tradeDate']
    previous=json.loads((out/'guru_market.json').read_text(encoding='utf-8')) if (out/'guru_market.json').exists() else {}
    companies=dict(previous.get('companies') or {})
    universe=[r for r in financials['universe'] if classify_company(r)['status']=='supported']
    # Missing target-day histories precede already verified ones, so bounded reruns resume.
    universe.sort(key=lambda r:((companies.get(r['symbol']) or {}).get('tradeDate')==trade,r['symbol']))
    if args.only_missing: universe=[r for r in universe if (companies.get(r['symbol']) or {}).get('tradeDate')!=trade]
    deadline=time.monotonic()+max(1,args.max_seconds); attempted=0; errors=0
    for start in range(0,len(universe),60):
        if time.monotonic()>=deadline: break
        group=universe[start:start+60]; symbols=[r['symbol'] for r in group]
        try:
            data=yf.download(symbols,period='2y',interval='1d',auto_adjust=False,group_by='ticker',threads=8,progress=False,timeout=15)
        except Exception:
            errors+=len(group); continue
        for row in group:
            attempted+=1; symbol=row['symbol']; bars=frame_bars(extract_frame(data,symbol),trade)
            if bars: companies[symbol]={'tradeDate':trade,'bars':bars,'sourceUrl':f'https://finance.yahoo.com/quote/{symbol}/history/'}
            else: errors+=1
        print(json.dumps({'marketProgress':attempted,'targetDate':trade,'stored':len(companies),'invalid':errors}),flush=True)
    keep={r['symbol'] for r in financials['universe']}
    companies={s:r for s,r in companies.items() if s in keep}
    value={'schemaVersion':1,'generatedAt':datetime.now(KST).isoformat(timespec='seconds'),'tradeDate':trade,
           'source':'Yahoo Finance 2y daily OHLCV; Close split-adjusted dividend-unadjusted',
           'collection':{'attempted':attempted,'invalidCount':errors},'companies':companies}
    atomic_json(out/'guru_market.json',value)
    print(json.dumps({'marketComplete':True,'tradeDate':trade,'validTargetDate':sum(r['tradeDate']==trade for r in companies.values())}))


if __name__=='__main__': main()
