"""Bounded official financial collection; visitors only read saved results."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guru_financials import normalize_reports, classify_company, KEYS
from guru_actions import refresh_action_windows, renormalize_cached_reports
from guru_snapshot import build_snapshot, publish_snapshot, atomic_json
from dart_financial_service import QUALITY_ACCOUNTS

KST = timezone(timedelta(hours=9))
OUT = ROOT/'static/data'


class DartLimit(Exception): pass
class BudgetLimit(Exception): pass
class ProviderError(Exception): pass


class DartClient:
    def __init__(self, key, corp_codes, max_requests, deadline):
        self.key, self.corp_codes = key, corp_codes
        self.requests, self.max_requests, self.deadline = 0, max_requests, deadline
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'ChartView financial evidence collector'
        self._sessions=threading.local(); self._sessions.session=self.session
        self._lock=threading.Lock(); self._limited=False

    def _get_session(self):
        if not getattr(self._sessions,'session',None):
            self._sessions.session=requests.Session()
            self._sessions.session.headers['User-Agent']='ChartView financial evidence collector'
        return self._sessions.session

    def get(self, endpoint, params):
        for attempt in range(2):
            with self._lock:
                if self._limited: raise DartLimit()
                if self.requests >= self.max_requests or time.monotonic() >= self.deadline: raise BudgetLimit()
                self.requests += 1
            try:
                r=self._get_session().get('https://opendart.fss.or.kr/api/'+endpoint,
                                   params={**params, 'crtfc_key': self.key}, timeout=12)
                r.raise_for_status(); data=r.json()
            except (requests.RequestException, ValueError):
                if attempt or self.requests>=self.max_requests: raise ProviderError('DART network error') from None
                continue
            if data.get('status') == '020':
                with self._lock:self._limited=True
                raise DartLimit()
            if data.get('status') not in {'000','013'}: raise ProviderError('DART status '+str(data.get('status')))
            return data

    def report(self, corp, year, basis, month=''):
        data=self.get('fnlttSinglAcntAll.json',{'corp_code':corp,'bsns_year':year,'reprt_code':'11011','fs_div':basis})
        if data.get('status') != '000': return None
        all_rows=data.get('list') or []
        receipts={r.get('rcept_no') for r in all_rows}
        if len(receipts)!=1: return None
        receipt=next(iter(receipts))
        if not re.fullmatch(r'\d{14}', receipt or ''): return None
        ids={aid for k in KEYS if k!='basicEps' for aid in QUALITY_ACCOUNTS[k][1]}
        names={name for k in KEYS if k!='basicEps' for name in QUALITY_ACCOUNTS[k][0]}
        rows=[r for r in all_rows if r.get('account_id') in ids or r.get('account_nm','').replace(' ','') in names
              or '주당' in r.get('account_nm','') or 'EarningsLossPerShare' in r.get('account_id','')]
        # Full-account responses lack dates. Cross-check against official major-account
        # income periods from the SAME receipt and financial basis, never acc_mt guesses.
        dates=self.get('fnlttSinglAcnt.json',{'corp_code':corp,'bsns_year':year,'reprt_code':'11011'})
        incomes=[r for r in dates.get('list',[]) if r.get('rcept_no')==receipt and r.get('fs_div')==basis and r.get('sj_div') in {'IS','CIS'}]
        periods={}
        for period in ('thstrm','frmtrm','bfefrmtrm'):
            found=set()
            for r in incomes:
                ds=re.findall(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',str(r.get(period+'_dt') or ''))
                if len(ds)==2:
                    found.add(tuple(f'{int(y):04}-{int(m):02}-{int(d):02}' for y,m,d in ds))
            if len(found)==1:
                start,end=next(iter(found));periods[period]={'start':start,'end':end}
        return {'year':year,'basis':basis,'periodEnd':periods.get('thstrm',{}).get('end'),'periods':periods,
                'receiptNo':receipt,'filingDate':f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}','rows':rows}

    def actions(self, corp, symbol, start, end):
        # Check all official disclosure names across the EPS observation interval.
        def invalid():
            raise ProviderError('DART disclosure pagination verification failed')
        def integer(value):
            if isinstance(value,bool) or not re.fullmatch(r'\d+',str(value)):
                invalid()
            return int(value)
        try:
            if not re.fullmatch(r'\d{8}',str(corp or '')):
                invalid()
            if not all(isinstance(day,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) for day in (start,end)):
                invalid()
            first,last=date.fromisoformat(start),date.fromisoformat(end)
            if first>last:invalid()
        except (TypeError,ValueError):
            invalid()
        events=[]; seen=set(); expected=None; page=1
        while True:
            # get() retains the existing shared request/deadline/020 limits.
            # A large issuer can exceed twenty pages without an artificial cap.
            data=self.get('list.json',{'corp_code':corp,'bgn_de':start.replace('-',''),'end_de':end.replace('-',''),
                                      'page_count':100,'page_no':page})
            if not isinstance(data,dict):invalid()
            if data.get('status')=='013':
                if page!=1 or data.get('list'):invalid()
                break
            if data.get('status')!='000':invalid()
            total,pages=integer(data.get('total_count')),integer(data.get('total_page'))
            current,size=integer(data.get('page_no')),integer(data.get('page_count'))
            rows=data.get('list')
            if (current!=page or size!=100 or pages!=(total+99)//100 or
                    not isinstance(rows,list) or len(rows)!=max(0,min(100,total-(page-1)*100)) or
                    expected is not None and expected!=(total,pages)):
                invalid()
            expected=total,pages
            for row in rows:
                if not isinstance(row,dict):invalid()
                receipt,observed,name=row.get('rcept_no'),row.get('rcept_dt'),row.get('report_nm')
                if (row.get('corp_code')!=corp or not isinstance(receipt,str) or not re.fullmatch(r'\d{14}',receipt) or
                        not re.fullmatch(r'\d{8}',str(observed or '')) or receipt in seen or
                        not isinstance(name,str) or not name.strip()):
                    invalid()
                try:day=date.fromisoformat(f'{observed[:4]}-{observed[4:6]}-{observed[6:]}')
                except (TypeError,ValueError):invalid()
                # rcept_no is an identifier; rcept_dt is the authoritative date.
                if not first<=day<=last:invalid()
                seen.add(receipt)
                if re.search(r'주식배당|주식분할|주식병합|무상증자|주식분할.*병합',row.get('report_nm','')):
                    events.append({'date':observed,'name':name,'receiptNo':receipt})
            if page>=pages:
                if len(seen)!=total:invalid()
                break
            page+=1
        return {'status':'verified','source':'OpenDART disclosures: split/reverse split/stock dividend/bonus issue',
                'start':start,'end':end,'events':events}

    def collect(self, row, previous):
        code=row.get('code') or row['symbol'].split('.')[0]
        corp=(self.corp_codes.get(code) or {}).get('corpCode')
        classification=classify_company(row)
        now=datetime.now(KST); target=now.year-1
        base={'symbol':row['symbol'],'classification':classification,'checkedAt':now.isoformat(timespec='seconds'),
              'collection':{'status':'complete','targetYear':target}}
        if classification['status']!='supported': return base
        if not corp:
            return {**base,'collection':{'status':'complete','reason':'DART 고유번호 연결 부족','targetYear':target}}
        # acc_mt is not proof of annual periods; dates come from the same filing.
        profile=(previous or {}).get('profile') or {}
        month=profile.get('acc_mt','')
        reports=[]
        latest=self.report(corp,target,'CFS',month)
        basis='CFS'
        if not latest: latest=self.report(corp,target,'OFS',month); basis='OFS'
        if not latest and now.month<4:
            target-=1
            latest=self.report(corp,target,'CFS',month); basis='CFS'
            if not latest: latest=self.report(corp,target,'OFS',month); basis='OFS'
            base['collection']['targetYear']=target
        if latest:
            reports.append(latest)
            # Always recheck the older filing: corrections also change historical EPS.
            old=self.report(corp,target-2,basis,month)
            if old: reports.append(old)
        start=f'{target-3}-01-01'; end=now.date().isoformat()
        try:
            actions=self.actions(corp,row['symbol'],start,end) if latest else {'status':'unknown'}
        except ProviderError as exc:
            actions={'status':'unknown','source':'OpenDART disclosures','start':start,'end':end,'reason':str(exc)}
        normalized=normalize_reports(reports,symbol=row['symbol'],classification=classification,actions=actions)
        return {**normalized,**base,'corpCode':corp,'reports':reports,'profile':profile,'actions':actions}


def refresh_cache(universe: list[dict], previous: dict, *, client, max_companies: int, max_requests: int, deadline: float, symbols: list[str] | None = None) -> dict:
    companies=dict(previous.get('companies') or {})
    current={r['symbol'] for r in universe}
    selected=None if symbols is None else set(symbols)
    if selected is not None and (not selected or selected-current):
        raise ValueError('Selected symbols must belong to the current KIND universe')
    attempted=0; errors=0; status='complete'; now=datetime.now(KST)
    def due(row):
        if selected is not None:return row['symbol'] in selected
        old=companies.get(row['symbol'])
        if not old: return True
        try: return (now-datetime.fromisoformat(old.get('lastAttemptAt') or old['checkedAt'])).total_seconds()>=86400
        except (KeyError,ValueError,TypeError): return True
    ordered=sorted(universe,key=lambda r:(r['symbol'] in companies, str((companies.get(r['symbol']) or {}).get('lastAttemptAt') or (companies.get(r['symbol']) or {}).get('checkedAt','')), r['symbol']))
    due_rows=[r for r in ordered if due(r)]
    index=0; stopped=False
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending={}
        while pending or (index<len(due_rows) and index<max_companies and not stopped):
            while len(pending)<2 and index<len(due_rows) and index<max_companies and not stopped:
                if client.requests>=max_requests or time.monotonic()>=deadline:
                    status='partial'; stopped=True; break
                row=due_rows[index];index+=1
                pending[pool.submit(client.collect,row,companies.get(row['symbol']))]=row
            if not pending:break
            finished,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in finished:
                row=pending.pop(future);old=companies.get(row['symbol'])
                try:companies[row['symbol']]=future.result()
                except DartLimit:status='rate_limited';stopped=True;continue
                except BudgetLimit:
                    if status!='rate_limited':status='partial'
                    stopped=True;continue
                except ProviderError as exc:
                    errors+=1
                    if old:companies[row['symbol']]={**old,'refreshError':str(exc),'lastAttemptAt':now.isoformat(timespec='seconds')}
                    else:companies[row['symbol']]={'symbol':row['symbol'],'classification':classify_company(row),
                        'checkedAt':now.isoformat(timespec='seconds'),'collection':{'status':'complete','reason':str(exc)}}
                attempted+=1
                if attempted%25==0:print(json.dumps({'progress':attempted,'requests':client.requests,'stored':len(companies)}),flush=True)
    if index<len(due_rows) and status=='complete':status='partial'
    companies={s:c for s,c in companies.items() if s in current}
    if errors and status=='complete': status='provider_errors'
    return {'generatedAt':now.isoformat(timespec='seconds'),'companies':companies,
            'collection':{'status':status,'attempted':attempted,'requests':client.requests,
                          'providerErrorCount':errors,
                          'storedCount':len(companies),'universeCount':len(current)}}


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--collect',action='store_true'); parser.add_argument('--max-companies',type=int,default=400)
    parser.add_argument('--symbols',help='Explicit comma-separated current KIND symbols to reverify within the existing budgets')
    parser.add_argument('--refresh-actions',action='store_true',help='Review only the missing official disclosure window, within the same request budget')
    parser.add_argument('--max-requests',type=int,default=2400); parser.add_argument('--max-seconds',type=int,default=1200)
    args=parser.parse_args()
    symbols=None
    if args.symbols is not None:
        symbols=[symbol.strip() for symbol in args.symbols.split(',')]
        if (not args.collect or not all(re.fullmatch(r'\d{6}\.(KS|KQ)',symbol) for symbol in symbols)):
            parser.error('--symbols requires --collect and comma-separated Korean tickers')
    prices=load_json(OUT/'screener.json',{})
    cache=renormalize_cached_reports(load_json(OUT/'guru_financials.json',{}))
    client=None
    if args.collect or args.refresh_actions:
        key=os.environ.get('DART_API_KEY','').strip()
        if not key: raise RuntimeError('DART_API_KEY is required')
        deadline=time.monotonic()+max(1,args.max_seconds)
        if args.collect:
            from scripts.generate_screener import load_universe
            universe=load_universe()
            if symbols is not None and set(symbols)-{row['symbol'] for row in universe}:
                parser.error('--symbols contains a ticker outside the current KIND universe')
        corp_codes=load_json(OUT/'dart_corp_codes.json',{}).get('companies',{})
        client=DartClient(key,corp_codes,max(1,args.max_requests),deadline)
    # Explicit selection performs those companies' full action checks below;
    # do not add an unrelated global disclosure scan to a targeted retry.
    if args.refresh_actions and symbols is None:
        cache=refresh_action_windows(cache,client=client,trade_date=prices.get('tradeDate'),
            checked_at=datetime.now(KST).isoformat(timespec='seconds'))
        print(json.dumps({'actionCollection':cache.get('actionCollection')}))
    if args.collect:
        action_metadata=cache.get('actionCollection')
        cache=refresh_cache(universe,cache,client=client,
                            max_companies=max(1,args.max_companies),max_requests=max(1,args.max_requests),deadline=deadline,symbols=symbols)
        if action_metadata:cache['actionCollection']=action_metadata
        cache['universe']=universe
        atomic_json(OUT/'guru_financials.json',cache)
    else:
        universe=cache.get('universe') or prices.get('stocks',[])
        if not cache:
            cache={'universe':universe,'companies':{},'collection':{'status':'pending'}}
            atomic_json(OUT/'guru_financials.json',cache)
    atomic_json(OUT/'guru_financials.json',cache)
    snapshot,evidence=build_snapshot(universe,prices,cache,generated_at=datetime.now(KST).isoformat(timespec='seconds'),
        market=load_json(OUT/'guru_market.json',{}),quarters=load_json(OUT/'guru_quarters.json',{}))
    publish_snapshot(snapshot,evidence,OUT)
    print(json.dumps({'tradeDate':snapshot['tradeDate'],'version':snapshot['snapshotVersion'],
        'collection':snapshot['collection'],'counts':{s:{k:v for k,v in d.items() if k.endswith('Count')} for s,d in snapshot['strategies'].items()}}))


if __name__=='__main__': main()
