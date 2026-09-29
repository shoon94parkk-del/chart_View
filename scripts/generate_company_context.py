"""Generate company/industry metadata for IDEA LAB independently of price data."""
from __future__ import annotations
import io, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests

KST=timezone(timedelta(hours=9))
OUT=Path('static/data/company_context.json')

def clean_text(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    text=str(value).strip()
    return '' if text.lower() == 'nan' else text

def build():
    rows=[]
    headers={'User-Agent':'Mozilla/5.0'}
    for market_type,market_name,suffix in [('stockMkt','KOSPI','.KS'),('kosdaqMkt','KOSDAQ','.KQ')]:
        response=requests.get(
            'https://kind.krx.co.kr/corpgeneral/corpList.do',
            params={'method':'download','marketType':market_type},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        frame=pd.read_html(io.StringIO(response.text))[0]
        for _,row in frame.iterrows():
            code=str(row['종목코드']).zfill(6)
            rows.append({
                'code':code,
                'symbol':f'{code}{suffix}',
                'name':clean_text(row.get('회사명')),
                'market':market_name,
                'industry':clean_text(row.get('업종')),
                'mainProducts':clean_text(row.get('주요제품')),
            })
    seen=set()
    companies=[]
    for row in rows:
        if row['symbol'] in seen:
            continue
        seen.add(row['symbol'])
        companies.append(row)
    companies.sort(key=lambda x:(x['market'],x['name'],x['symbol']))
    payload={
        'updated':datetime.now(KST).isoformat(timespec='seconds'),
        'source':'KRX KIND 상장법인목록',
        'count':len(companies),
        'companies':companies,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Saved {len(companies)} company context rows')

if __name__=='__main__':
    build()
