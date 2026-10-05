"""Deterministic Chart View criteria, inspired by principles, not recommendations."""
from __future__ import annotations
from datetime import date
import math

EPSILON = 1e-9
CRITERIA_VERSION = 'cv-gurus-v1'


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evaluate_company(company: dict, quote: dict | None, *, strategy: str) -> dict:
    if strategy not in {'buffett', 'lynch'}:
        raise ValueError('Unknown strategy')
    result = {'status': 'insufficient', 'metrics': {}, 'checks': [], 'reasons': [],
              'criteriaVersion': CRITERIA_VERSION}
    def stop(status, reason):
        result['status'] = status
        result['reasons'] = [reason]
        return result
    classification = (company.get('classification') or {}).get('status')
    if classification == 'unsupported': return stop('unsupported', '일반기업 조건 비교 지원 제외')
    if classification != 'supported': return stop('insufficient', '업종·상품 유형 확인 부족')
    if (company.get('collection') or {}).get('status') == 'pending':
        return stop('pending', '연간 재무자료 수집 대기')
    if not quote or quote.get('symbol') != company.get('symbol') or not finite(quote.get('price')) or quote['price'] <= 0:
        return stop('insufficient', '동일 종목의 기준 거래일 종가 확인 부족')
    try:
        trade_date = date.fromisoformat(quote['date'])
    except (KeyError, TypeError, ValueError):
        return stop('insufficient', '가격 기준일 확인 부족')
    if quote.get('currency') != 'KRW' or company.get('currency') != 'KRW' or company.get('basis') not in {'CFS', 'OFS'}:
        return stop('insufficient', '통화·재무 기준 확인 부족')
    sources = company.get('sources') or {}
    if not sources or any(str(account.get('filingDate') or '9999') > quote['date']
                          for accounts in sources.values() for account in accounts.values()):
        return stop('insufficient', '공시 시점·출처 확인 부족')
    rows = company.get('annual') or []
    latest = company.get('annualReportYear')
    if not isinstance(latest, int) or latest != trade_date.year - 1:
        return stop('insufficient', '최근 목표 사업연도 확인 부족')
    by_year = {r.get('year'): r for r in rows}
    if len(by_year) != len(rows) or any(y not in by_year for y in range(latest-3, latest+1)):
        return stop('insufficient', '연속 4개 연도 자료 확인 부족')
    rows = [by_year[y] for y in range(latest-3, latest+1)]
    required = ['equity', 'liabilities', 'operatingCashFlow'] + (['netIncome'] if strategy == 'buffett' else ['basicEps'])
    needed_rows = rows[1:] if strategy == 'buffett' else rows
    if any(not finite(r.get(key)) for r in needed_rows for key in required) or not finite(rows[0].get('equity')):
        return stop('insufficient', '필수 계정 누락·금액 확인 부족')
    if any(r['equity'] <= 0 for r in rows):
        return stop('failed', '양수 자본 조건 미충족')
    debt = rows[-1]['liabilities']/rows[-1]['equity']*100
    metrics = result['metrics']
    metrics['debtRatio'] = debt
    def check(key, label, value, threshold, passed):
        result['checks'].append({'id': key, 'label': label, 'value': value, 'threshold': threshold, 'passed': passed})
    if strategy == 'buffett':
        income = [r['netIncome'] for r in rows[1:]]
        cash = [r['operatingCashFlow'] for r in rows[1:]]
        roe = [rows[i]['netIncome']/((rows[i-1]['equity']+rows[i]['equity'])/2)*100 for i in range(1,4)]
        avg = sum(roe)/3
        metrics.update(roeAvg3=avg, roeMin3=min(roe), roeLatest=roe[-1],
                       cashConversion3=(sum(cash)/sum(income)*100 if sum(income)>0 else None))
        check('profit', '3년 연속 흑자', min(income), '각 연도 순이익 >0', min(income)>0)
        check('roe', '꾸준한 자본수익성', avg, '각 연도 ≥10% · 평균 ≥15%', min(roe)>=10-EPSILON and avg>=15-EPSILON)
        check('cash', '이익의 현금 뒷받침', metrics['cashConversion3'], '각 연도 OCF >0 · 3년 합계 ≥순이익', min(cash)>0 and sum(cash)>=sum(income)-EPSILON)
        result['basis'] = {'roe': '공시 총자본 기준 ROE', 'cash': '영업현금흐름'}
    else:
        comparable = company.get('epsComparability') or {}
        if comparable.get('status') != 'verified' or comparable.get('end', '') < quote['date']:
            return stop('insufficient', '보통주 EPS·기업행동 비교 기준 확인 부족')
        eps = [r['basicEps'] for r in rows]
        if min(eps) <= 0: return stop('failed', '4년 양수 EPS 조건 미충족')
        growth = ((eps[-1]/eps[0])**(1/3)-1)*100
        pe = quote['price']/eps[-1]
        peg = pe/growth if growth>0 else None
        metrics.update(epsCagr3=growth, annualPE=pe, historicalPEG=peg, basicEps=eps[-1])
        check('growth', '주당이익 성장', growth, '3년 10~30% · 최근 연도 증가', 10-EPSILON<=growth<=30+EPSILON and eps[-1]>eps[-2])
        check('valuation', '성장 대비 가격', peg, '과거 실적 기준 PEG ≤1', peg is not None and pe>0 and peg<=1+EPSILON)
        check('cash', '최근 영업현금 유입', rows[-1]['operatingCashFlow'], '최근 OCF >0', rows[-1]['operatingCashFlow']>0)
        result['basis'] = {'per': '최근 연간 실적 기준 PER', 'peg': '과거 3년 EPS 성장 기준 PEG'}
    check('debt', '부채 부담', debt, '부채총계 / 자본총계 ≤100%', debt<=100+EPSILON)
    result['status'] = 'matched' if all(c['passed'] for c in result['checks']) else 'failed'
    result['reasons'] = [c['label'] for c in result['checks'] if c['passed'] == (result['status']=='matched')]
    return result
