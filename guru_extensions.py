"""Explicit Chart View adaptations of growth, trend and quality/value principles."""
from datetime import date
from bisect import bisect_left, bisect_right
import re

from guru_rules import finite, EPSILON
from guru_financials import _eps_account, amount
from dart_financial_service import _pick_account, REVENUE_NAMES, REVENUE_IDS

STRATEGIES = ('buffett', 'lynch', 'oneil', 'minervini', 'greenblatt')


def expected_quarter(as_of):
    d=date.fromisoformat(as_of)
    if (d.month,d.day)>=(11,16): return d.year,3
    if (d.month,d.day)>=(8,16): return d.year,2
    if (d.month,d.day)>=(5,16): return d.year,1
    if (d.month,d.day)>=(4,1): return d.year-1,4
    return d.year-1,3


def normalize_quarter(report):
    year,quarter=report.get('year'),report.get('quarter')
    if not isinstance(year,int) or quarter not in (1,2,3) or report.get('basis') not in {'CFS','OFS'}: return None
    end=f'{year}-{quarter*3:02}-{(31 if quarter in (1,4) else 30):02}'
    receipt=report.get('receiptNo','')
    if not re.fullmatch(r'\d{14}',receipt): return None
    if report.get('filingDate')!=f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}' or report['filingDate']<end: return None
    # Official major-account cumulative dates validate fiscal alignment; the full
    # account API's IS amounts are reported THREE MONTHS, not cumulative add_amount.
    if (report.get('periods') or {}).get('thstrm')!={'start':f'{year}-01-01','end':end}: return None
    rows=report.get('rows') or []
    eps=_eps_account(rows); sales=_pick_account(rows,REVENUE_NAMES,REVENUE_IDS)
    if any(not a or a.get('currency')!='KRW' or a.get('rcept_no')!=receipt for a in (eps,sales)): return None
    values={'basicEps':amount(eps.get('thstrm_amount')),'priorBasicEps':amount(eps.get('frmtrm_q_amount')),
            'revenue':amount(sales.get('thstrm_amount')),'priorRevenue':amount(sales.get('frmtrm_q_amount'))}
    if any(v is None for v in values.values()): return None
    return {**values,'year':year,'quarter':quarter,'basis':report['basis'],'currency':'KRW',
        'periodStart':f'{year}-{quarter*3-2:02}-01','periodEnd':end,
        'priorPeriodStart':f'{year-1}-{quarter*3-2:02}-01','priorPeriodEnd':end.replace(str(year),str(year-1),1),
        'filingDate':report['filingDate'],'receiptNo':receipt,
        'method':'OpenDART full accounts reported three months',
        'sourceUrl':f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}',
        'accounts':{k:{'accountId':a.get('account_id'),'accountName':a.get('account_nm'),
                       'currentField':'thstrm_amount','priorField':'frmtrm_q_amount'} for k,a in [('basicEps',eps),('revenue',sales)]}}


def technical_metrics(bars, trade_date):
    if not isinstance(bars,list) or len(bars)<253: return None
    dates=[]
    for b in bars:
        if not isinstance(b,list) or len(b)!=5 or not all(finite(v) for v in b[1:]): return None
        try: day=date.fromisoformat(b[0])
        except (ValueError,TypeError): return None
        if day.weekday()>4 or b[1]<=0 or not 0<b[3]<=b[1]<=b[2] or b[4]<0: return None
        dates.append(b[0])
    if dates!=sorted(set(dates)) or dates[-1]!=trade_date: return None
    close=[b[1] for b in bars]; highs=[b[2] for b in bars]; lows=[b[3] for b in bars]; volumes=[b[4] for b in bars]
    mean=lambda rows:sum(rows)/len(rows)
    t={'tradeDate':trade_date,'price':close[-1],'barCount':len(bars),'startDate':dates[0],
       'sma50':mean(close[-50:]),'sma150':mean(close[-150:]),'sma200':mean(close[-200:]),
       'sma200Prior20':mean(close[-220:-20]),'high52':max(highs[-252:]),'low52':min(lows[-252:]),
       'return252':(close[-1]/close[-253]-1)*100,
       'source':'Yahoo Finance daily OHLCV','priceBasis':'Yahoo Close: split-adjusted, dividend-unadjusted',
       'breakoutDate':None,'breakoutLevel':None,'breakoutVolumeRatio':None,'breakoutExtensionPct':None}
    # Last five completed sessions; pivot and 50-session volume baseline exclude
    # each breakout session. Never use a present/future bar in its prior threshold.
    for i in range(len(bars)-5,len(bars)):
        level=max(highs[i-55:i]); baseline=mean(volumes[i-50:i])
        if close[i]>level and baseline>0 and volumes[i]/baseline>=1.4:
            t.update(breakoutDate=dates[i],breakoutLevel=level,breakoutVolumeRatio=volumes[i]/baseline,
                     breakoutExtensionPct=(close[-1]/level-1)*100)
    return t


def relative_strength(rows, eligible_count):
    returns=sorted(r['return252'] for r in rows.values())
    n=len(returns)
    for r in rows.values():
        left,right=bisect_left(returns,r['return252']),bisect_right(returns,r['return252'])
        r['relativeStrengthPercentile']=100*(left+right)/(2*n)
        r['rsCoverage']=n/eligible_count if eligible_count else 0
        r['rsUniverseCount']=eligible_count; r['rsObservedCount']=n


def evaluate_extension(company, quote, *, strategy, technical=None, quarter=None):
    if strategy not in STRATEGIES[2:]: raise ValueError('Unknown extension')
    result={'status':'insufficient','metrics':{},'checks':[],'reasons':[],'criteriaVersion':'cv-gurus-v2'}
    def stop(status,reason): result.update(status=status,reasons=[reason]); return result
    def check(key,label,value,threshold,passed,unit='%'):
        result['checks'].append(dict(id=key,label=label,value=value,threshold=threshold,passed=bool(passed),unit=unit))
    def finish():
        result['status']='matched' if all(c['passed'] for c in result['checks']) else 'failed'
        result['reasons']=[c['label'] for c in result['checks'] if c['passed']==(result['status']=='matched')]
        return result
    classification=company.get('classification') or {}
    if classification.get('status')=='unsupported': return stop('unsupported','일반기업 조건 비교 지원 제외')
    if classification.get('status')!='supported': return stop('insufficient','업종·상품 유형 확인 부족')
    if strategy=='greenblatt' and re.search(r'전기.*공급|가스.*공급|수도.*공급|증기.*공급',classification.get('industry','')):
        return stop('unsupported','금융·유틸리티 비교 지원 제외')
    if not quote or quote.get('symbol')!=company.get('symbol') or quote.get('currency')!='KRW' or not finite(quote.get('price')) or quote['price']<=0:
        return stop('insufficient','동일 종목의 기준 거래일 종가 확인 부족')
    try: d=date.fromisoformat(quote['date'])
    except (TypeError,ValueError,KeyError): return stop('insufficient','가격 기준일 확인 부족')
    if strategy in {'minervini','oneil'}:
        if not technical or technical.get('tradeDate')!=quote['date'] or abs(technical.get('price',0)/quote['price']-1)>.001:
            return stop('insufficient','동일 기준일 253거래일 OHLCV 확인 부족')
        if not finite(technical.get('relativeStrengthPercentile')) or technical.get('rsCoverage',0)<.9:
            return stop('insufficient','상대강도 비교 시장의 90% 자료 확인 부족')
        result['metrics'].update(technical)
    if strategy=='minervini':
        t=technical; price=quote['price']
        check('trend','이동평균 정렬',t['sma50'],'종가 >50일 >150일 >200일',price>t['sma50']>t['sma150']>t['sma200'],'원')
        change=(t['sma200']/t['sma200Prior20']-1)*100
        result['metrics']['sma200Change20']=change
        result['metrics']['distance52HighPct']=(price/t['high52']-1)*100
        check('slope','200일선 상승',change,'20거래일 전보다 상승',change>0)
        check('low','저점에서 상승',(price/t['low52']-1)*100,'52주 저가 대비 ≥30%',price>=t['low52']*1.3-EPSILON)
        check('high','고점 부근',result['metrics']['distance52HighPct'],'52주 고가 대비 하락 ≤25%',price>=t['high52']*.75-EPSILON)
        check('strength','시장 내 상대강도',t['relativeStrengthPercentile'],'252거래일 수익률 백분위 ≥70',t['relativeStrengthPercentile']>=70-EPSILON)
        result['basis']={'method':'50·150·200일 추세 · 한국시장 단순 252거래일 수익률 백분위; IBD RS Rating 아님'}
        return finish()
    if company.get('refreshError'): return stop('insufficient','공시 갱신 확인 실패 · 이전 자료 보존')
    if (company.get('collection') or {}).get('status')=='pending': return stop('pending','연간 재무자료 수집 대기')
    if company.get('currency')!='KRW' or company.get('basis') not in {'CFS','OFS'}: return stop('insufficient','통화·재무 기준 확인 부족')
    sources=company.get('sources') or {}
    if not sources or any(str(a.get('filingDate') or '9999')>quote['date'] for accounts in sources.values() for a in accounts.values()):
        return stop('insufficient','공시 시점·출처 확인 부족')
    latest=company.get('annualReportYear'); earliest=d.year-(2 if d.month<4 else 1)
    if not isinstance(latest,int) or not earliest<=latest<=d.year-1: return stop('insufficient','최근 목표 사업연도 확인 부족')
    rows=company.get('annual') or []; by_year={r.get('year'):r for r in rows}
    if len(by_year)!=len(rows) or latest not in by_year: return stop('insufficient','연간 자료 확인 부족')
    last=by_year[latest]
    comparable=company.get('epsComparability') or {}
    if comparable.get('status')!='verified' or comparable.get('end','')<quote['date']:
        return stop('insufficient','보통주 EPS·기업행동 비교 기준 확인 부족')
    if strategy=='greenblatt':
        if any(not finite(last.get(k)) for k in ('assets','netIncome','basicEps')): return stop('insufficient','필수 계정 누락·금액 확인 부족')
        if last['assets']<=0 or last['basicEps']<=0: return stop('failed','양수 자산·EPS 조건 미충족')
        roa=last['netIncome']/last['assets']*100; pe=quote['price']/last['basicEps']
        result['metrics'].update(annualROA=roa,annualPE=pe,basicEps=last['basicEps'])
        check('quality','자산수익성',roa,'연간 순이익 / 기말 총자산 ≥25%',roa>=25-EPSILON)
        check('value','실적 대비 가격',pe,'연간 실적 PER 5~20배',5-EPSILON<=pe<=20+EPSILON,'배')
        result['basis']={'method':'ROA/PER 대안 · EV 매직포뮬러 아님','ranking':'조건 충족 기업을 PER 오름차순으로 최대30개; 동률 종목코드 순'}
        return finish()
    if any(y not in by_year for y in range(latest-3,latest+1)): return stop('insufficient','연속 4개 연도 자료 확인 부족')
    annual=[by_year[y] for y in range(latest-3,latest+1)]
    if any(not finite(r.get('basicEps')) for r in annual) or any(not finite(last.get(k)) for k in ('netIncome','equity')) or not finite(annual[-2].get('equity')):
        return stop('insufficient','필수 계정 누락·금액 확인 부족')
    eps=[r['basicEps'] for r in annual]
    if min(eps)<=0 or min(last['equity'],annual[-2]['equity'])<=0: return stop('failed','양수 EPS·자본 조건 미충족')
    growth=[(eps[i]/eps[i-1]-1)*100 for i in range(1,4)]
    roe=last['netIncome']/((last['equity']+annual[-2]['equity'])/2)*100
    result['metrics'].update(epsGrowthMin3=min(growth),roeLatest=roe)
    check('annual','연속 이익 성장',min(growth),'최근 3개 연도 EPS 각각 ≥25% 성장',min(growth)>=25-EPSILON)
    check('roe','자본수익성',roe,'최근 총자본 ROE ≥17%',roe>=17-EPSILON)
    # A proven necessary-condition failure needs no extra paid/provider requests.
    if not all(c['passed'] for c in result['checks']): return finish()
    if quarter is None: return stop('pending','단일 분기 EPS·매출 공시 수집 대기')
    if not quarter.get('available',True): return stop('insufficient','단일 분기 EPS·매출 비교 자료 확인 부족')
    if (quarter.get('year'),quarter.get('quarter'))!=expected_quarter(quote['date']) or quarter.get('basis')!=company['basis'] or quarter.get('currency')!='KRW' or not quarter.get('filingDate') or quarter['filingDate']>quote['date']:
        return stop('insufficient','최근 동일 기준 분기·공시 시점 확인 부족')
    verified=normalize_quarter(quarter.get('report')) if quarter.get('report') else None
    if not verified and quarter.get('method')!='OpenDART full accounts reported three months':
        return stop('insufficient','단일 분기 공시 계산 기준 확인 부족')
    if verified and any(quarter.get(k)!=verified.get(k) for k in ('basicEps','priorBasicEps','revenue','priorRevenue','filingDate','basis','periodStart','periodEnd')):
        return stop('insufficient','분기 원계정과 계산 결과 불일치')
    if any(not finite(quarter.get(k)) for k in ('basicEps','priorBasicEps','revenue','priorRevenue')):
        return stop('insufficient','필수 분기 계정 누락')
    if min(quarter['basicEps'],quarter['priorBasicEps'],quarter['revenue'],quarter['priorRevenue'])<=0: return stop('failed','양수 분기 EPS·매출 비교 조건 미충족')
    eg=(quarter['basicEps']/quarter['priorBasicEps']-1)*100; sg=(quarter['revenue']/quarter['priorRevenue']-1)*100
    t=technical; extension=t.get('breakoutExtensionPct'); volume=t.get('breakoutVolumeRatio')
    result['metrics'].update(quarterEpsGrowth=eg,quarterSalesGrowth=sg,quarterYear=quarter['year'],quarterNumber=quarter['quarter'])
    check('quarter','분기 EPS 성장',eg,'전년 같은 단일 분기 ≥25%',eg>=25-EPSILON)
    check('sales','분기 매출 성장',sg,'전년 같은 단일 분기 ≥25%',sg>=25-EPSILON)
    check('strength','시장 내 상대강도',t['relativeStrengthPercentile'],'252거래일 수익률 백분위 ≥80',t['relativeStrengthPercentile']>=80-EPSILON)
    check('breakout','거래량 동반 돌파',volume,'최근5일 내 이전55일 고가 돌파 · 이전50일 평균량 ≥1.4배',bool(t.get('breakoutDate')) and finite(volume) and volume>=1.4-EPSILON,'배')
    check('extension','돌파 후 위치',extension,'현재 종가가 돌파선 위 0~5%',finite(extension) and -EPSILON<=extension<=5+EPSILON)
    result['basis']={'method':'CAN SLIM의 정량 일부 · 신제품/기관 수급/차트 패턴/시장 추세 미확인'}
    return finish()
