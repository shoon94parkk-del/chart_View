"""Reuse the existing private DART credential/budgets for necessary quarterly evidence."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.generate_guru_screening import DartClient, DartLimit, BudgetLimit, ProviderError, load_json, KST
from guru_financials import classify_company
from guru_extensions import expected_quarter, normalize_quarter, evaluate_extension, technical_metrics, relative_strength
from guru_snapshot import atomic_json


def collect_report(client,corp,year,quarter,basis):
    if quarter==4: return None # Never subtract cumulative weighted-average EPS.
    code={1:'11013',2:'11012',3:'11014'}[quarter]
    params={'corp_code':corp,'bsns_year':year,'reprt_code':code}
    full=client.get('fnlttSinglAcntAll.json',{**params,'fs_div':basis})
    if full.get('status')!='000': return None
    rows=full.get('list') or []; receipts={r.get('rcept_no') for r in rows}
    if len(receipts)!=1: return None
    receipt=next(iter(receipts))
    if not receipt or len(receipt)!=14 or not receipt.isdigit(): return None
    major=client.get('fnlttSinglAcnt.json',params)
    incomes=[r for r in major.get('list',[]) if r.get('rcept_no')==receipt and r.get('fs_div')==basis and r.get('sj_div') in {'IS','CIS'}]
    import re
    periods=set()
    for row in incomes:
        found=re.findall(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',str(row.get('thstrm_dt') or ''))
        if len(found)==2: periods.add(tuple(f'{int(y):04}-{int(m):02}-{int(d):02}' for y,m,d in found))
    if len(periods)!=1: return None
    start,end=next(iter(periods))
    # Retain only the actual EPS/revenue source rows, no provider key.
    selected=[r for r in rows if r.get('sj_div') in {'IS','CIS'} and ('EarningsLossPerShare' in r.get('account_id','') or '주당' in r.get('account_nm','') or r.get('account_id') in {'ifrs-full_Revenue','ifrs_Revenue','ifrs-full_RevenueFromContractsWithCustomers'} or r.get('account_nm','').replace(' ','') in {'매출액','매출','영업수익','수익(매출액)','수익'})]
    report={'year':year,'quarter':quarter,'basis':basis,'receiptNo':receipt,'filingDate':f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}',
            'periods':{'thstrm':{'start':start,'end':end}},'rows':selected}
    normalized=normalize_quarter(report)
    return {**normalized,'report':report} if normalized else {'available':False,'year':year,'quarter':quarter,'report':report}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-companies',type=int,default=400)
    parser.add_argument('--max-requests',type=int,default=1000);parser.add_argument('--max-seconds',type=int,default=300);args=parser.parse_args()
    out=ROOT/'static/data'; f=load_json(out/'guru_financials.json',{});p=load_json(out/'screener.json',{})
    market=load_json(out/'guru_market.json',{});previous=load_json(out/'guru_quarters.json',{})
    companies=dict(previous.get('companies') or {}); trade=p['tradeDate']; year,quarter=expected_quarter(trade)
    quotes={r['symbol']:{**r,'currency':'KRW'} for r in p['stocks'] if r['date']==trade}
    tech={}; identities={r['symbol']:r for r in f['universe']}; eligible=[r for r in f['universe'] if classify_company(r)['status']=='supported']
    for s,row in (market.get('companies') or {}).items():
        value=technical_metrics(row.get('bars'),trade)
        if value and s in identities and classify_company(identities[s])['status']=='supported' and s in quotes and abs(value['price']/quotes[s]['price']-1)<=.001: tech[s]=value
    relative_strength(tech,sum(r['symbol'] in quotes and quotes[r['symbol']].get('price',0)>0 for r in eligible))
    needed=[]
    for identity in eligible:
        s=identity['symbol']; c={**((f.get('companies') or {}).get(s) or {}),'classification':classify_company(identity)}
        result=evaluate_extension(c,quotes.get(s),strategy='oneil',technical=tech.get(s),quarter=None)
        if result['status']=='pending' and '분기' in result['reasons'][0]: needed.append(identity)
    needed.sort(key=lambda r:((companies.get(r['symbol']) or {}).get('checkedAt',''),r['symbol']))
    key=os.environ.get('DART_API_KEY','').strip()
    if not key: raise RuntimeError('Existing DART_API_KEY is required')
    deadline=time.monotonic()+max(1,args.max_seconds)
    client=DartClient(key,{},max(1,args.max_requests),deadline)
    corp_codes=load_json(out/'dart_corp_codes.json',{}).get('companies',{})
    attempted=0;errors=0;status='complete'
    for identity in needed:
        s=identity['symbol'];old=companies.get(s) or {};now=datetime.now(KST)
        if (old.get('year'),old.get('quarter'))==(year,quarter) and old.get('checkedAt') and (now-datetime.fromisoformat(old['checkedAt'])).total_seconds()<86400: continue
        if attempted>=args.max_companies or client.requests>=args.max_requests or time.monotonic()>=deadline: status='partial';break
        c=f['companies'][s];corp=c.get('corpCode') or (corp_codes.get(s.split('.')[0]) or {}).get('corpCode')
        try:
            result=collect_report(client,corp,year,quarter,c['basis']) if corp else None
            companies[s]={**(result or {'available':False,'year':year,'quarter':quarter}), 'checkedAt':now.isoformat(timespec='seconds')}
        except DartLimit: status='rate_limited'; break
        except BudgetLimit: status='partial'; break
        except ProviderError:
            errors+=1;companies[s]={'available':False,'year':year,'quarter':quarter,'checkedAt':now.isoformat(timespec='seconds'),'reason':'DART quarterly verification failed'}
        attempted+=1
        if attempted%10==0:print(json.dumps({'quarterProgress':attempted,'requests':client.requests,'needed':len(needed)}),flush=True)
    atomic_json(out/'guru_quarters.json',{'schemaVersion':1,'generatedAt':datetime.now(KST).isoformat(timespec='seconds'),
        'collection':{'status':status,'attempted':attempted,'requests':client.requests,'providerErrorCount':errors,'necessaryCompanyCount':len(needed)},
        'companies':{s:r for s,r in companies.items() if s in identities}})
    print(json.dumps({'quarterCollection':status,'attempted':attempted,'requests':client.requests,'necessary':len(needed),'errors':errors}))


if __name__=='__main__':main()
