"""Dated public observations and explicit assumptions for the NPS model revision 2.

Amounts are KRW trillions, return inputs are percent. Proxy prices are not NPS
portfolio marks. Private local NAV changes remain unobserved, not estimated income.
"""
from __future__ import annotations
import calendar
import datetime as dt
import html
import math
import re
import time
import urllib.request


def cash_breakdown(inputs, assets, scale=1):
    cash_base=next(a['base'] for a in assets if a['id']=='cash')*scale
    if not 0<=inputs['cashWeight']<=1 or not 0<=inputs['cashNonFinancialWeight']<=1-inputs['cashWeight']:
        raise ValueError('Invalid cash component weights')
    if not 0<=inputs['flowIncomeFraction']<=1 or min(inputs['cashIncomeReturn'],inputs['hedgeCarryReturn'])<=-100:
        raise ValueError('Invalid cash income assumptions')
    short=cash_base*inputs['cashWeight'];nonfinancial=cash_base*inputs['cashNonFinancialWeight']
    principal=sum(a['base']*scale*a['foreignShare'] for a in assets)*inputs['hedgeRatio']/100
    income=short*inputs['cashIncomeReturn']/100
    carry=principal*inputs['hedgeCarryReturn']/100
    flow_income=inputs['netFlow']*inputs['flowIncomeFraction']*inputs['cashIncomeReturn']/100
    gain=income+carry+flow_income
    return {'shortTermBase':short,'nonFinancialBase':nonfinancial,'reconciliationBase':cash_base-short-nonfinancial,
            'shortTermIncome':income,'hedgePrincipal':principal,'hedgeCarry':carry,'externalFlowIncome':flow_income,
            'effectiveReturnPercent':gain/cash_base*100,'projected':cash_base+gain}


def model_inputs(config, core, market_date, pct_return):
    start=config['baseline']['date'];m=config['realism'];days=(dt.date.fromisoformat(market_date)-dt.date.fromisoformat(start)).days
    flow=m['externalFlows'];net=(flow['contributionsBillion']+flow['subsidiesBillion']-flow['expendituresBillion'])/1000
    observed_days=(dt.date.fromisoformat(flow['observedThrough'])-dt.date.fromisoformat(flow['observedFrom'])).days+1
    if observed_days<=0 or days<0:raise ValueError('Invalid external flow period')
    kr=pct_return(core['357870.KS'],start,market_date);usd=pct_return(core['BIL'],start,market_date)
    return {'assetModel':2,'domesticBondReturn':pct_return(core['273130.KS'],start,market_date),
            'alternativeReturn':0.,'netFlow':net/observed_days*days,'domesticFlow':0.,
            'cashWeight':m['cash']['shortTermBase']/m['cash']['groupBase'],
            'cashNonFinancialWeight':m['cash']['nonFinancialBase']/m['cash']['groupBase'],
            'cashIncomeReturn':kr,'hedgeCarryReturn':((1+kr/100)/(1+usd/100)-1)*100,
            'flowIncomeFraction':.5}


def same_date_prices(chart, start, end, currency='USD'):
    """A comparison cannot substitute another currency or an earlier close."""
    if not chart or chart.get('currency')!=currency or chart.get('error'):return False
    points=chart.get('points',{})
    return all(isinstance(points.get(day),dict) and all(
        isinstance(points[day].get(key),(int,float)) and math.isfinite(points[day][key]) and points[day][key]>0
        for key in ('close','adjustedClose')) for day in (start,end))


def model_metadata(config, core, market_date, inputs, pct_return):
    import copy
    m=copy.deepcopy(config['realism']);start=config['baseline']['date']
    m['externalFlows'].update(observedNetFlow=(m['externalFlows']['contributionsBillion']+m['externalFlows']['subsidiesBillion']-m['externalFlows']['expendituresBillion'])/1000,
                             projectedNetFlow=inputs['netFlow'],projectedDays=(dt.date.fromisoformat(market_date)-dt.date.fromisoformat(start)).days,
                             projectionThrough=market_date)
    m['alternatives']['economicReturnPct']=sum(a['weightPct']/100*pct_return(core[a['proxySymbol']],start,market_date) for a in m['alternatives']['composition'])
    m['alternatives']['economicProxyReturnPct']=m['alternatives']['economicReturnPct']
    proxy=core.get('AGGG.L');unhedged=None
    if same_date_prices(proxy,start,market_date):
        candidate=pct_return(proxy,start,market_date)
        if math.isfinite(candidate) and candidate>-100:unhedged=candidate
    m['overseasBonds'].update(unhedgedProxyReturnPct=unhedged,
        unhedgedProxyStatus='available' if unhedged is not None else 'unavailable',unhedgedProxyDate=market_date)
    m['domesticBonds']['governmentComparisonReturnPct']=.5*pct_return(core['114260.KS'],start,market_date)+.5*pct_return(core['148070.KS'],start,market_date)
    m['cash'].update(incomeReturnPct=inputs['cashIncomeReturn'],usdIncomeReturnPct=pct_return(core['BIL'],start,market_date),
                     hedgeCarryReturnPct=inputs['hedgeCarryReturn'])
    return m


def assumption_cases(inputs,assets,metadata,calculate):
    settings=[('beta-low','국내주식 코스피 민감도 0.9',{'beta':.9}),('beta-high','국내주식 코스피 민감도 1.1',{'beta':1.1}),
      ('hedge-none','환헤지 0% 가정',{'hedgeRatio':0}),('hedge-high','환헤지 30% 가정',{'hedgeRatio':30}),
      ('flows-none','공시 이후 외부 순유입 0 가정',{'netFlow':0}),('flows-double','외부 순유입 외삽의 2배',{'netFlow':inputs['netFlow']*2}),
      ('bond-unhedged-proxy','해외채권 AGGG 비헤지 대용지표',{'bondReturn':metadata['overseasBonds']['unhedgedProxyReturnPct']}),
      ('alternative-economic-proxy','대체투자 상장 대용지표 경제가치',{'alternativeReturn':metadata['alternatives']['economicReturnPct']})]
    cases=[];unavailable=[];results=[calculate(inputs,assets)]
    for identity,label,patch in settings:
        if identity=='bond-unhedged-proxy' and (patch['bondReturn'] is None or metadata['overseasBonds'].get('unhedgedProxyStatus')=='unavailable'):
            unavailable.append({'id':identity,'label':label,'reason':'동일 기준일의 가격을 확인하지 못해 비교를 제공하지 않아요.'})
            continue
        result=calculate({**inputs,**patch},assets);results.append(result)
        cases.append({'id':identity,'label':label,'patch':patch,**{key:result[key] for key in ('weight','gap','adjustment')}})
    return {'kind':'assumption-cases','note':'한 번에 가정 하나만 바꾼 범위이며 통계적 신뢰구간이나 실제 오차의 상하한이 아닙니다.',
      'cases':cases,'lowWeight':min(r['weight'] for r in results),'highWeight':max(r['weight'] for r in results),
      'lowAdjustment':min(r['adjustment'] for r in results),'highAdjustment':max(r['adjustment'] for r in results),
      **({'unavailable':unavailable} if unavailable else {})}


def monthly_report_date(document):
    """Only matching monthly portfolio notices can establish the observed month.

    A newer date elsewhere (press release, copyright or holding disclosure) is
    never substituted for the balance date. Missing/malformed notice fails closed.
    """
    text=html.unescape(re.sub(r'<[^>]*>',' ',document))
    periods=re.findall(r'자산군별\s*포트폴리오\s*운용\s*현황\s*및\s*수익률\s*\(\s*(20\d{2})\s*[.년/-]\s*(\d{1,2})\s*월\s*\)',text)
    dates=[]
    for y,m in periods:
        year,month=int(y),int(m)
        dates.append(dt.date(year,month,calendar.monthrange(year,month)[1]).isoformat())
    if not dates:raise ValueError('Monthly portfolio notice not found')
    return max(dates)


def monthly_check(config,deadline):
    baseline=config['baseline']['date'];url=config['realism']['monthlySourceUrl'];checked=dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        if time.monotonic()>=deadline:raise TimeoutError('Collection budget reached')
        request=urllib.request.Request(url,headers={'User-Agent':'ChartView/1.0 public-data-research https://github.com/shoon94parkk-del/chart_View'})
        with urllib.request.urlopen(request,timeout=min(12,max(.1,deadline-time.monotonic()))) as response:
            body=response.read(2_000_001)
        if len(body)>2_000_000:raise ValueError('Official homepage response exceeds limit')
        observed=monthly_report_date(body.decode('utf-8'))
        # A monthly balance cannot refer to a future/uncompleted month. Treat a
        # corrupt official notice as unavailable, never as a new reviewed NAV.
        if observed>checked[:10]:raise ValueError('Official monthly balance date is in the future')
        if observed<baseline:raise ValueError('Official homepage notice is older than reviewed baseline')
        return {'status':'review-required' if observed>baseline else 'verified','checkedAt':checked,'reportDate':observed,
                'baselineDate':baseline,'sourceUrl':url}
    except Exception as error:
        return {'status':'unavailable','attemptedAt':checked,'lastVerifiedAt':config['realism']['verifiedAt'],
                'baselineDate':baseline,'reportDate':baseline,'sourceUrl':url,'reason':str(error)[:180]}
