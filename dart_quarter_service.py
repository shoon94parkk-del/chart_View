"""Independent cached standalone quarter history. Never delays core detail APIs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
import threading
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from dart_financial_service import _get_statement, _static_row, KST
from dart_business_service import _corp_codes, _redis_client, _stock_code

router = APIRouter()
_CACHE = {}
_RUNNING = set()
_LOCK = threading.Lock()
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dart-quarters")
TTL = 86400
STATIC_PATH = Path(__file__).parent / 'static/data/dart_financial_quarters.json'
_STATIC = (0, {})

def slots(end, count):
    n = end[0] * 4 + end[1] - 1
    return [(v // 4, v % 4 + 1) for v in range(n-count+1, n+1)]

def source(packet):
    receipt = str(packet.get('rceptNo') or '')
    return f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}' if len(receipt)==14 and receipt.isdigit() else None

def assemble_quarters(packets, end):
    by = {(p['year'], p['quarter']): p for p in packets}
    rows = {}
    for year, q in slots(end, 12):
        p = by.get((year, q))
        row = dict(year=year, quarter=q, revenue=None, operatingProfit=None, available=False, sourceUrls=[], method=None)
        if p:
            row.update(currency=p.get('currency'), basis=p.get('basis'))
            direct = p.get('singleQuarter') or {}
            prev = by.get((year, q-1))
            compatible = prev and all(prev.get(k)==p.get(k) and p.get(k) for k in ('basis','currency'))
            if q<4 and all(isinstance(direct.get(k), (int,float)) for k in ('revenue','operatingProfit')):
                row.update(revenue=direct['revenue'], operatingProfit=direct['operatingProfit'], method='reported_three_months', sourceUrls=[source(p)])
            elif q==1:
                row.update(revenue=p.get('revenue'), operatingProfit=p.get('operatingProfit'), method='reported_q1', sourceUrls=[source(p)])
            elif compatible and all(isinstance(x.get(k),(int,float)) for x in (p,prev) for k in ('revenue','operatingProfit')):
                row.update(revenue=p['revenue']-prev['revenue'], operatingProfit=p['operatingProfit']-prev['operatingProfit'], method='annual_minus_q3' if q==4 else 'cumulative_difference', sourceUrls=[source(p),source(prev)])
            row['sourceUrls'] = [url for url in row['sourceUrls'] if url]
            row['available'] = all(isinstance(row[k],(int,float)) for k in ('revenue','operatingProfit')) and bool(row['sourceUrls'])
            if not row['available']:
                row.update(revenue=None, operatingProfit=None)
        rows[(year,q)] = row
    for (year,q), row in rows.items():
        old = rows.get((year-1,q)) or {}
        compatible = old.get('available') and row.get('available') and all(old.get(k)==row.get(k) and row.get(k) for k in ('basis','currency'))
        for key, prior, growth in [('revenue','priorRevenue','revenueGrowth'),('operatingProfit','priorOperatingProfit','profitGrowth')]:
            row[prior] = old.get(key) if compatible else None
            row[growth] = (row[key]/old[key]-1)*100 if compatible and old[key]>0 else None
        row['margin'] = row['operatingProfit']/row['revenue']*100 if row['available'] and row['revenue']>0 else None
    shown = [rows[s] for s in slots(end,8)]
    four = shown[-4:]
    ttm = None
    if all(r['available'] for r in four) and len({(r['basis'],r['currency']) for r in four})==1:
        sales, profit = sum(r['revenue'] for r in four), sum(r['operatingProfit'] for r in four)
        ttm = dict(revenue=sales, operatingProfit=profit, margin=profit/sales*100 if sales>0 else None,
                   start=f"{four[0]['year']} Q{four[0]['quarter']}",end=f"{end[0]} Q{end[1]}",currency=four[-1]['currency'],basis=four[-1]['basis'])
    return dict(quarters=shown, ttm=ttm, available=any(r['available'] for r in shown))

def _read(code):
    global _STATIC
    candidates=[]
    try:
        stamp=STATIC_PATH.stat().st_mtime
        if stamp!=_STATIC[0]:_STATIC=(stamp,json.loads(STATIC_PATH.read_text(encoding='utf-8')))
        row=(_STATIC[1].get('companies') or {}).get(code)
        if isinstance(row,dict) and row.get('available') and row.get('stockCode')==code and row.get('schemaVersion')==1:candidates.append(row)
    except (OSError,ValueError):pass
    try:
        client = _redis_client()
        row = json.loads(client.get(f'chartview:dart-quarters:v1:{code}') or 'null') if client else None
        if isinstance(row,dict) and row.get('stockCode')==code and row.get('schemaVersion')==1:candidates.append(row)
    except Exception:
        pass
    def freshness(row):
        q=(row.get('quarters') or [{}])[-1]
        return (q.get('year',0),q.get('quarter',0),max(q.get('sourceUrls') or ['']),row.get('checkedAt',''))
    return max(candidates,key=freshness,default=None)

def _collect(code, ticker):
    key = os.environ.get('DART_API_KEY','').strip()
    now = datetime.now(KST)
    result = dict(ticker=ticker,stockCode=code,schemaVersion=1,source='OpenDART',checkedAt=now.isoformat(),state='unavailable',available=False)
    if not key:
        return dict(result,reason='api_key_unavailable')
    company = _corp_codes(key).get(code)
    if not company or not company.get('corpCode'):
        return dict(result,reason='corp_code_unavailable')
    end = (now.year,3 if now.month>=11 else 2 if now.month>=8 else 1 if now.month>=5 else 0)
    if end[1]==0: end=(now.year-1,4)
    baseline = _static_row(code) or {}
    basis = 'OFS' if baseline.get('basis')=='별도재무제표' else 'CFS'
    # Establish one basis before collecting; never mix OFS fallback per quarter.
    if not baseline.get('available'):
        def probe(year, report, candidate):
            try:return _get_statement(key,company['corpCode'],year,report,candidate)
            except Exception:return None
        consolidated=probe(end[0],{1:'11013',2:'11012',3:'11014',4:'11011'}[end[1]],'CFS') or probe(now.year-1,'11011','CFS')
        if not consolidated and probe(now.year-1,'11011','OFS'):basis='OFS'
    failures=[]
    def fetch(slot):
        y,q = slot
        try:
            row = _get_statement(key,company['corpCode'],y,{1:'11013',2:'11012',3:'11014',4:'11011'}[q],basis)
            if not row:return None
            if q==4:
                annual = next((r for r in row['years'] if r['year']==y),None)
                if not annual:return None
                row = dict(annual,currency=row['currency'],rceptNo=row['rceptNo'])
            return dict(row,year=y,quarter=q,basis=basis)
        except Exception:
            failures.append(slot)
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        packets = [r for r in pool.map(fetch,slots(end,13)) if r]
    success_count=len(packets)
    old = _read(code) or {}
    old_packets = old.get('packets') or []
    merged = {(p['year'],p['quarter']):p for p in old_packets if p.get('basis')==basis}
    for p in packets:
        previous=merged.get((p['year'],p['quarter']))
        if not previous or str(p['rceptNo'])>=str(previous['rceptNo']):merged[(p['year'],p['quarter'])]=p
    packets=list(merged.values())
    if not packets:return dict(result,reason='statement_unavailable')
    actual_end=max((p['year'],p['quarter']) for p in packets)
    data=assemble_quarters(packets,actual_end)
    if not success_count:result['checkedAt']=old.get('checkedAt')
    return dict(result,**data,state='ready' if data['available'] else 'unavailable',packets=packets,basis='연결재무제표' if basis=='CFS' else '별도재무제표',
                refreshFailed=not bool(success_count),partialRefresh=bool(failures) and bool(success_count),successfulReports=success_count,failedReports=len(failures))

def _refresh(code,ticker):
    try:
        row=_collect(code,ticker)
        with _LOCK:
            old=_CACHE.get(code)
            if old and old[1].get('available') and not row.get('available'):
                row=dict(old[1],refreshFailed=True)
            _CACHE[code]=(time.time(),row)
        if row.get('available'):
            try:
                client=_redis_client()
                if client:client.set(f'chartview:dart-quarters:v1:{code}',json.dumps(row,ensure_ascii=False))
            except Exception:pass
    except Exception:
        with _LOCK:
            old=_CACHE.get(code)
            _CACHE[code]=(time.time(),dict(old[1],refreshFailed=True) if old else dict(available=False,state='error',reason='provider_unavailable'))
    finally:
        with _LOCK:_RUNNING.discard(code)

def fetch_quarters(ticker, force=False):
    code=_stock_code(ticker)
    with _LOCK:cached=_CACHE.get(code)
    if not cached:
        row=_read(code)
        if row:
            try:stamp=datetime.fromisoformat(row['checkedAt']).timestamp()
            except (ValueError,KeyError):stamp=0
            cached=(stamp,row)
            with _LOCK:_CACHE[code]=cached
    with _LOCK:
        if (force or not cached or time.time()-cached[0]>= (TTL if cached[1].get('available') else 60)) and code not in _RUNNING:
            if len(_RUNNING)<8:
                _RUNNING.add(code);_POOL.submit(_refresh,code,ticker)
        running=code in _RUNNING
    if not cached:return dict(available=False,state='loading' if running else 'busy',source='OpenDART')
    # Internal filing packets never need to be transmitted to the browser.
    return {k:v for k,v in dict(cached[1],refreshing=running).items() if k!='packets'}

@router.get('/api/financial-quarters')
def financial_quarters(ticker: str=Query(...,min_length=6,max_length=12), refresh: bool=False):
    try:_stock_code(ticker)
    except ValueError:raise HTTPException(status_code=400,detail='Domestic ticker required')
    return fetch_quarters(ticker.upper(),force=refresh)
