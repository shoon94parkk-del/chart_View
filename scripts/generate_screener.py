"""Precompute a fast KOSPI/KOSDAQ technical screener.

Daily AI data is fail-closed: stale rows may never masquerade as today's full-market scan.
"""
from __future__ import annotations
import io, json, math, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests
import yfinance as yf

KST=timezone(timedelta(hours=9)); OUT=Path('static/data/screener.json'); META_OUT=Path('static/data/screener_meta.json')
BATCH_SIZE=80; PERIOD='8mo'; MIN_ROWS=120; MIN_EXACT_COVERAGE=0.90

def finite(value,digits=2):
    try:
        value=float(value)
        if math.isnan(value) or math.isinf(value): return None
        return round(value,digits)
    except (TypeError,ValueError): return None

def expected_trade_date(now=None):
    """Expected Korean regular-session date for post-close weekday runs.
    Holiday truth is ultimately established by market data; weekend is deterministic.
    """
    day=(now or datetime.now(KST)).date()
    while day.weekday()>=5: day-=timedelta(days=1)
    return day.isoformat()

def load_universe():
    stocks=[]; headers={'User-Agent':'Mozilla/5.0'}
    for market_type,market_name,suffix in [('stockMkt','KOSPI','.KS'),('kosdaqMkt','KOSDAQ','.KQ')]:
        r=requests.get('https://kind.krx.co.kr/corpgeneral/corpList.do',params={'method':'download','marketType':market_type},headers=headers,timeout=30); r.raise_for_status()
        frame=pd.read_html(io.StringIO(r.text))[0]
        for _,row in frame.iterrows():
            code=str(row['종목코드']).zfill(6); stocks.append({'code':code,'name':str(row['회사명']).strip(),'market':market_name,'symbol':f'{code}{suffix}'})
    seen=set(); result=[]
    for item in stocks:
        if item['symbol'] not in seen: seen.add(item['symbol']); result.append(item)
    return result

def rsi14(close):
    d=close.diff(); gain=d.clip(lower=0); loss=-d.clip(upper=0); ag=gain.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); al=loss.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    if ag.empty or pd.isna(ag.iloc[-1]) or pd.isna(al.iloc[-1]): return None
    g,l=ag.iloc[-1],al.iloc[-1]
    if l==0:return 100.0 if g>0 else 0.0
    return finite(100-100/(1+g/l),1)

def pct_from(close,p):
    if len(close)<=p:return None
    old,new=close.iloc[-p-1],close.iloc[-1]
    return finite((new/old-1)*100,2) if pd.notna(old) and pd.notna(new) and old>0 else None

def extract_frame(data,symbol):
    if data is None or data.empty:return None
    if not isinstance(data.columns,pd.MultiIndex):return data.copy()
    l0,l1=data.columns.get_level_values(0),data.columns.get_level_values(1)
    try:
        if symbol in l0:return data[symbol].copy()
        if symbol in l1:return data.xs(symbol,axis=1,level=1).copy()
    except Exception:return None
    return None

def download_batch(symbols):
    last=None
    for attempt in range(3):
        try:
            data=yf.download(tickers=symbols,period=PERIOD,interval='1d',group_by='ticker',auto_adjust=False,threads=True,progress=False,timeout=30)
            if data is not None and not data.empty:return data
        except Exception as exc:last=exc
        time.sleep(1.5*(attempt+1))
    if last: raise last
    return pd.DataFrame()

def _technical_score(rsi,macd,signal,pm,ps,price,ma20,ma60,mid,upper,vr,r5,r20):
    rs=7 if rsi is not None and 45<=rsi<=65 else 5 if rsi is not None and (40<=rsi<45 or 65<rsi<=70) else 3 if rsi is not None and 35<=rsi<40 else 0 if rsi is not None and rsi>75 else 1 if rsi is not None else 0
    ms=0
    if None not in (macd,signal): ms=6 if macd>signal and None not in(pm,ps) and pm<=ps else 5 if macd>signal and macd>0 else 4 if macd>signal else 2 if None not in(pm,ps) and macd-signal>pm-ps else 0
    mas=6 if None not in(price,ma20,ma60) and price>ma20>ma60 else 5 if None not in(price,ma20,ma60) and price>ma20 and ma20>=ma60*.99 else 3 if None not in(price,ma20) and price>ma20 else 2 if None not in(price,ma60) and price>ma60 else 0
    bs=0
    if None not in(price,mid,upper) and upper>mid:
        pos=(price-mid)/(upper-mid); bs=6 if .10<=pos<=.75 else 5 if 0<=pos<.10 else 4 if .75<pos<=1 else 3 if price>=mid else 1
    vs=5 if vr is not None and 1.2<=vr<=2.5 and (r5 or 0)>0 else 4 if vr is not None and vr>=1 and (r5 or 0)>0 else 2 if (r20 or 0)>0 else 0
    pen=(2 if rsi is not None and rsi>75 else 0)+(2 if r5 is not None and r5>25 else 0)+(2 if r20 is not None and r20>60 else 0)
    return max(0,min(30,rs+ms+mas+bs+vs-pen)),{'rsi':rs,'macd':ms,'trend':mas,'bollinger':bs,'volumeMomentum':vs,'chasePenalty':pen}

def build_row(meta,frame):
    if frame is None or frame.empty or 'Close' not in frame.columns or 'Volume' not in frame.columns:return None
    close=pd.to_numeric(frame['Close'],errors='coerce'); volume=pd.to_numeric(frame['Volume'],errors='coerce'); valid=close.notna()&(close>0); close=close[valid]; volume=volume.reindex(close.index).fillna(0)
    if len(close)<MIN_ROWS:return None
    ma20s,ma60s,ma120s=close.rolling(20).mean(),close.rolling(60).mean(),close.rolling(120).mean(); e12,e26=close.ewm(span=12,adjust=False).mean(),close.ewm(span=26,adjust=False).mean(); macds=e12-e26; sigs=macds.ewm(span=9,adjust=False).mean(); std=close.rolling(20).std(ddof=0); upper=ma20s+2*std; lower=ma20s-2*std
    price,prev=finite(close.iloc[-1],0),finite(close.iloc[-2],0); ma20,ma60,ma120=finite(ma20s.iloc[-1],0),finite(ma60s.iloc[-1],0),finite(ma120s.iloc[-1],0); rsi=rsi14(close); macd,signal,pm,ps=finite(macds.iloc[-1],2),finite(sigs.iloc[-1],2),finite(macds.iloc[-2],2),finite(sigs.iloc[-2],2); mid,up,lo=finite(ma20s.iloc[-1],0),finite(upper.iloc[-1],0),finite(lower.iloc[-1],0)
    v20=volume.tail(20).mean(); vr=finite(volume.iloc[-1]/v20,2) if v20 and v20>0 else None; avg=finite((close.tail(20)*volume.tail(20)).mean(),0); change=finite((price/prev-1)*100,2) if price and prev else None; r5,r20,r60=pct_from(close,5),pct_from(close,20),pct_from(close,60)
    score,breakdown=_technical_score(rsi,macd,signal,pm,ps,price,ma20,ma60,mid,up,vr,r5,r20); dt=close.index[-1]; dt=dt.date().isoformat() if hasattr(dt,'date') else str(dt)[:10]
    return {'code':meta['code'],'symbol':meta['symbol'],'name':meta['name'],'market':meta['market'],'date':dt,'price':price,'previousClose':prev,'change1d':change,'rsi14':rsi,'macd':macd,'macdSignal':signal,'volumeRatio':vr,'avgValue20':avg,'ma20':ma20,'ma60':ma60,'ma120':ma120,'bbMid':mid,'bbUpper':up,'bbLower':lo,'above20':bool(ma20 and price>ma20),'above60':bool(ma60 and price>ma60),'cross20':bool(pd.notna(ma20s.iloc[-2]) and close.iloc[-2]<=ma20s.iloc[-2] and close.iloc[-1]>ma20s.iloc[-1]),'aligned':bool(ma20 and ma60 and ma120 and price>ma20>ma60>ma120),'ret5':r5,'ret20':r20,'ret60':r60,'technicalScore':score,'technicalBreakdown':breakdown,'score':score}

def process_group(group):
    symbols=[x['symbol'] for x in group]
    try:data=download_batch(symbols)
    except Exception as exc:print(f'Batch failed ({len(symbols)}): {exc}');return []
    return [r for m in group if (r:=build_row(m,extract_frame(data,m['symbol']))) is not None]

def build():
    universe=load_universe(); print(f'Universe: {len(universe)} KOSPI/KOSDAQ companies'); rows=[]
    for start in range(0,len(universe),BATCH_SIZE):
        group=universe[start:start+BATCH_SIZE]; print(f'Downloading batch {start//BATCH_SIZE+1}/{math.ceil(len(universe)/BATCH_SIZE)}...'); br=process_group(group)
        if len(br)<len(group)*.5:
            print('Weak batch; retrying in groups of 20'); br=[]
            for s in range(0,len(group),20): br.extend(process_group(group[s:s+20])); time.sleep(.4)
        rows.extend(br); time.sleep(.5)
    if not rows:raise RuntimeError('Yahoo batch download returned no usable Korean stocks')
    freshest=max(r['date'] for r in rows); exact=[r for r in rows if r['date']==freshest]; coverage=len(exact)/len(universe)
    expected=expected_trade_date()
    print(f'Freshest={freshest}; expected={expected}; exact coverage={len(exact)}/{len(universe)} ({coverage:.1%})')
    # Scheduled post-close runs must never publish an old snapshot or a partial pseudo-full-market scan.
    if os.getenv('REQUIRE_KST_TRADE_DATE')=='1':
        if freshest!=expected: raise RuntimeError(f'STALE_MARKET_DATE: expected {expected}, provider freshest {freshest}')
        if coverage<MIN_EXACT_COVERAGE: raise RuntimeError(f'INSUFFICIENT_EXACT_COVERAGE: {len(exact)}/{len(universe)} ({coverage:.1%})')
    rows=exact; rows.sort(key=lambda x:(x.get('technicalScore') or 0,x.get('avgValue20') or 0),reverse=True)
    payload={'updated':datetime.now(KST).isoformat(timespec='seconds'),'tradeDate':freshest,'count':len(rows),'universeCount':len(universe),'exactDateCount':len(exact),'exactDateCoverage':round(coverage,4),'scoreModel':'technical 30 only; final recommendation = fundamental/industry 70 + technical 30','source':'KIND listing + Yahoo Finance batched daily prices; exact-date fail-closed','stocks':rows}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); META_OUT.write_text(json.dumps({k:payload[k] for k in ('updated','tradeDate','count','universeCount','exactDateCount','exactDateCoverage','scoreModel','source')},ensure_ascii=False,separators=(',',':')),encoding='utf-8'); print(f'Saved exact-date {len(rows)} stocks')

if __name__=='__main__':build()
