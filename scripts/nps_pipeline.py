#!/usr/bin/env python3
"""Revalue the disclosed NPS basket after a common completed market session.

Never called by the API. No credentials or model services are required. A failed
or partial collection exits nonzero before replacing the last valid publication.
Official monthly balances and CUSIP mappings are deliberately reviewed inputs.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent / 'nps'))
import quotes

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'scripts/nps/config.json'
CORE = {'ACWI': 'USD', 'BNDW': 'USD', 'KRW=X': 'KRW', '^KS11': 'KRW',
        '114260.KS': 'KRW', '148070.KS': 'KRW'}
UTC = dt.timezone.utc


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def common_session(core, cutoff, baseline):
    """All six independent series must provide a finite positive same-date close."""
    days = None
    for symbol, currency in CORE.items():
        chart = core[symbol]
        if chart.get('currency') != currency:
            raise ValueError(f'{symbol}: unexpected currency')
        points = chart.get('points', {})
        base = points.get(baseline)
        if not base or not all(quotes.finite_positive(base.get(k)) for k in ('close', 'adjustedClose')):
            raise ValueError(f'{symbol}: baseline session missing')
        observed = {d for d, p in points.items() if baseline < d <= cutoff
                    and all(quotes.finite_positive(p.get(k)) for k in ('close', 'adjustedClose'))}
        days = observed if days is None else days & observed
    if not days:
        raise ValueError('No common completed market session')
    chosen = max(days)
    if (dt.date.fromisoformat(cutoff) - dt.date.fromisoformat(chosen)).days > 5:
        raise ValueError('Common completed close is more than five calendar days old')
    return chosen


def pct_return(chart, start, end):
    return (chart['points'][end]['adjustedClose'] / chart['points'][start]['adjustedClose'] - 1) * 100


def validate_config(config):
    b=config['baseline'];i=config['inputs'];assets=config['assetBaseline'];f=config['filing']
    if any(i[k]!=b[v] for k,v in [('baseTotal','total'),('baseDomestic','domestic'),('baseKospi','kospi')]):
        raise ValueError('Reviewed baseline and model input values disagree')
    if not math.isclose(sum(a['base'] for a in assets)+b['domestic'],b['total'],rel_tol=1e-10):
        raise ValueError('Asset baseline does not reconcile to official total')
    if not math.isclose(next(a['base'] for a in assets if a['id']=='equity'),b['overseas'],rel_tol=1e-10):
        raise ValueError('Foreign equity baseline mismatch')
    if not f['reportDate']<b['date'] or f['filedDate']<f['reportDate']:
        raise ValueError('Reviewed filing/baseline chronology invalid')
    if any(a['base']<=0 or not 0<=a['foreignShare']<=1 for a in assets):
        raise ValueError('Invalid asset amount or foreign exposure')
    if i['assetModel']!=1:
        raise ValueError('Scheduled pipeline requires multiasset model')


def calculate(inputs, asset_baseline):
    """Same KRW-trillion model used by the original reviewed simulator."""
    s = inputs
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in s.values()):
        raise ValueError('Inputs must be finite numbers')
    if not 0 < s['baseDomestic'] < s['baseTotal'] or s['baseKospi'] <= 0 or s['kospi'] <= 0:
        raise ValueError('Invalid baseline or KOSPI')
    if not 0 < s['target'] < s['target'] + s['saa'] + s['taa'] < 100 or not 0 <= s['hedgeRatio'] <= 100:
        raise ValueError('Invalid policy percentages')
    scale = (s['baseTotal'] - s['baseDomestic']) / sum(a['base'] for a in asset_baseline)
    assets = []
    for a in asset_baseline:
        base = a['base'] * scale
        r = s[a['returnKey']]
        if r <= -100:
            raise ValueError('Return cannot be <= -100%')
        market_gain = base * r / 100
        fx_gain = (base + market_gain) * a['foreignShare'] * (1 - s['hedgeRatio']/100) * s['fxReturn']/100
        overlay = (base + market_gain + fx_gain) * s['otherReturn']/100
        assets.append({**a, 'base': base, 'returnPercent': r, 'marketGain': market_gain,
                       'fxGain': fx_gain, 'overlayGain': overlay, 'projected': base + market_gain + fx_gain + overlay})
    market_other = sum(a['projected'] for a in assets)
    funded_other = market_other + s['netFlow']
    domestic = s['baseDomestic'] * (s['kospi']/s['baseKospi'])**s['beta'] + s['domesticFlow']
    other = funded_other - s['domesticFlow']
    total = domestic + other
    if min(domestic, other) < 0 or total <= 0:
        raise ValueError('Invalid projected balances')
    def threshold(p):
        w = p/100
        market_domestic = (w * funded_other - s['domesticFlow']) / (1-w)
        return s['baseKospi'] * (market_domestic/s['baseDomestic'])**(1/s['beta']) if market_domestic > 0 else None
    fixed_other = s['baseTotal'] - s['baseDomestic'] + s['netFlow'] - s['domesticFlow']
    return {'weight': domestic/total*100, 'gap': domestic/total*100-s['target'],
            'adjustment': s['target']/100*total-domestic, 'total': total, 'domestic': domestic, 'other': other,
            'targetKospi': threshold(s['target']), 'saaKospi': threshold(s['target']+s['saa']),
            'taaKospi': threshold(s['target']+s['saa']+s['taa']), 'assets': assets,
            'marketGain': sum(a['marketGain'] for a in assets), 'fxGain': sum(a['fxGain'] for a in assets),
            'overlayGain': sum(a['overlayGain'] for a in assets), 'otherBeforeFlows': market_other,
            'fixedOtherWeight': domestic/(domestic+fixed_other)*100 if fixed_other >= 0 else None}


def sensitivity(inputs, assets):
    results = [calculate(inputs, assets)]
    for direction in [-1, 1]:
        for hedge in [max(0, inputs['hedgeRatio']-15), min(100, inputs['hedgeRatio']+15)]:
            candidate = {**inputs, 'equityReturn': inputs['equityReturn']+direction*2,
                         'bondReturn': inputs['bondReturn']+direction,
                         'domesticBondReturn': inputs['domesticBondReturn']+direction*.5,
                         'alternativeReturn': inputs['alternativeReturn']+direction*2, 'hedgeRatio': hedge}
            results.append(calculate(candidate, assets))
    return {'lowWeight': min(r['weight'] for r in results), 'highWeight': max(r['weight'] for r in results),
            'lowAdjustment': min(r['adjustment'] for r in results), 'highAdjustment': max(r['adjustment'] for r in results)}


def filing_check(config, deadline):
    known = config['filing']
    checked = dt.datetime.now(UTC).isoformat()
    try:
        if time.monotonic() >= deadline:
            raise TimeoutError('Collection budget reached')
        request = urllib.request.Request(known['sourceSubmissionsUrl'], headers={
            'User-Agent': 'ChartView/1.0 public-data-research https://github.com/shoon94parkk-del/chart_View'})
        with urllib.request.urlopen(request, timeout=min(12, max(.1, deadline-time.monotonic()))) as response:
            data = json.loads(response.read(8_000_000))
        recent = data['filings']['recent']
        filings = [{'accession': recent['accessionNumber'][i], 'reportDate': recent['reportDate'][i],
                    'filedDate': recent['filingDate'][i], 'form': form}
                   for i, form in enumerate(recent['form']) if form in ('13F-HR', '13F-HR/A')]
        if not filings:
            raise ValueError('No 13F in recent SEC submissions')
        latest = max(filings, key=lambda f: (f['reportDate'], f['filedDate'], f['accession']))
        return {'status': 'verified' if latest['accession'] == known['accession'] else 'review-required',
                'checkedAt': checked, **latest}
    except Exception as error:
        return {'status': 'unavailable', 'attemptedAt': checked, 'lastVerifiedAt': known['checkedAsOf'],
                'reportDate': known['reportDate'], 'reason': str(error)[:180]}


def quality_gate(rows, config, previous_details=None):
    if len(rows) != config['filing']['positionCount']:
        raise ValueError('13F position count mismatch')
    report_total = sum(r['reportValueUSD'] for r in rows)
    if abs(report_total-config['filing']['reportedValueUsd']) > .01:
        raise ValueError('13F USD report total mismatch')
    if len({r['cusip'] for r in rows}) != len(rows):
        raise ValueError('Duplicate CUSIP')
    coverage = sum(r['reportValueUSD'] for r in rows if r['valid']) / report_total
    if coverage < .99:
        raise ValueError(f'13F report-value quote coverage {coverage:.4%} below 99%')
    # A transient provider failure must not silently reclassify yesterday's known
    # holdings to a different benchmark. Complex new actions require review too.
    previous_direct = {r['cusip'] for r in (previous_details or {}).get('rows', []) if r['method'] == 'direct'}
    newly_invalid = [r['ticker'] for r in rows if not r['valid'] and r['cusip'] in previous_direct]
    if newly_invalid:
        raise ValueError('Previously priced holdings failed validation: '+', '.join(newly_invalid))
    return coverage


def build_snapshot(config, core, rows, market_date, latest_check, generated_at):
    base = config['baseline']; start = base['date']
    coverage = quality_gate(rows, config)
    direct = [r for r in rows if r['valid']]
    base_usd = sum(r['baselineMarketValueUSD'] for r in direct)
    end_usd = sum(r['currentTotalReturnValueUSD'] for r in direct)
    if base_usd <= 0:
        raise ValueError('Empty priced sleeve')
    fx_start = core['KRW=X']['points'][start]['close']
    fx_end = core['KRW=X']['points'][market_date]['close']
    base_krw = base_usd * fx_start/1e12
    residual = base['overseas'] - base_krw
    if residual < 0:
        raise ValueError('13F slice exceeds official foreign equities; reject double count')
    direct_return = (end_usd/base_usd-1)*100
    residual_return = pct_return(core['ACWI'], start, market_date)
    blended = (base_krw*direct_return + residual*residual_return)/base['overseas']
    days = (dt.date.fromisoformat(market_date)-dt.date.fromisoformat(start)).days
    inputs = {**config['inputs'], 'kospi': core['^KS11']['points'][market_date]['close'],
              'equityReturn': blended, 'bondReturn': pct_return(core['BNDW'], start, market_date),
              'domesticBondReturn': .5*pct_return(core['114260.KS'],start,market_date)+.5*pct_return(core['148070.KS'],start,market_date),
              'alternativeReturn': 6*days/365+.25*blended, 'cashReturn': 3*days/365,
              'fxReturn': (fx_end/fx_start-1)*100}
    assets = [dict(a) for a in config['assetBaseline']]
    for a in assets:
        if a['id']=='domesticBond': a['method']='국채 3년·10년 ETF 50:50 조정종가 수익률 추정'
        if a['id']=='bond': a['method']='BNDW 분배금 재투자 조정종가 수익률 + 환율'
    total_report = config['filing']['reportedValueUsd']
    detail_rows = [{'ticker':r['ticker'],'issuer':r['issuer'],'cusip':r['cusip'],'shares':r['shares'],
                    'reportValueUSD':r['reportValueUSD'],'weightPct':r['reportValueUSD']/total_report*100,
                    'totalReturnPct':r.get('totalReturn',0)*100 if r['valid'] else None,
                    'method':'direct' if r['valid'] else 'residual',
                    'currentValueUSD':r.get('currentTotalReturnValueUSD') if r['valid'] else None,
                    'currentMarketValueUSD':r.get('currentMarketValueUSD') if r['valid'] else None,
                    'baselineValueUSD':r.get('baselineMarketValueUSD') if r['valid'] else None,
                    'flags':r['flags'],'sourceUrl':r.get('sourceUrl'),'prices':r.get('prices'),
                    'rawSha256':r.get('rawSha256'),
                    'sharesOnCurrentBasis':r.get('sharesOnCurrentBasis'),
                    'actualSharesAtBaseline':r.get('actualSharesAtBaseline'),
                    'splitFactorAfterReport':r.get('splitFactorAfterReport'),
                    'splitFactorAfterBaseline':r.get('splitFactorAfterBaseline'),
                    'reportPriceCheck':r.get('reportPriceCheck'),
                    'events':r.get('events'),
                    'corporateActionReview':r.get('corporateActionReview')} for r in rows]
    version = hashlib.sha256(canonical({'marketDate':market_date,'inputs':inputs,'rows':detail_rows}).encode()).hexdigest()[:16]
    filename = f'holdings-{version}.json'
    observations = {symbol:{'name':chart.get('name'),'currency':chart['currency'],
                           'baseline':chart['points'][start], 'current':chart['points'][market_date],
                           'sourceUrl':chart['sourceUrl'],'retrievedAt':chart['retrievedAt'],'rawSha256':chart['rawSha256']}
                    for symbol,chart in core.items()}
    warnings = ['추정치입니다. 공시 이후 실제 매매·납입·급여지급을 확인할 수 없어 순유입과 순매매는 0으로 가정합니다.',
                '13F의 보고 수량을 유지하고 가격·배당·검증 가능한 주식분할만 반영합니다. 실제 현재 보유명세가 아닙니다.',
                '국내주식은 코스피 가격지수에 민감도 1을 적용합니다. 실제 종목 구성·배당 재투자·추적 오차는 반영되지 않습니다.',
                '13F 미평가·미포함 해외주식은 ACWI로 추정하며 미국 외 자산만을 뜻하지 않습니다.',
                '국내채권은 국채 3년·10년 ETF 50:50 대용치이며 실제 국민연금 채권 수익률과 다릅니다.',
                '같은 거래일의 시장별 종가이며 미국·한국·외환의 종료시각이 서로 다릅니다.',
                '대체투자 연 6% + 해외주식 수익률 × 0.25, 단기자산 연 3%, 환헤지 15%를 가정합니다.',
                '자동 갱신은 Yahoo의 같은 일별 환율 시계열과 국내채권 ETF 대용치를 사용합니다. 이전 별도 사이트의 환율 제공자·금리 근사 방식과 값이 다를 수 있습니다.',
                f"공식 기금 기준일 {start}의 자산 구성은 새 월별 공시를 검증할 때 갱신합니다.",
                '목표 20.8% 및 SAA 6%p·TAA 2%p는 기존 검증 자료에 따른 시나리오이며 실제 매매 예고가 아닙니다.']
    if latest_check['status']=='review-required':
        warnings.append(f"새 SEC {latest_check.get('form')}({latest_check['reportDate']})가 발견됐습니다. 종목 대응 검증 전까지 {config['filing']['reportDate']} 보고 수량을 사용합니다.")
    elif latest_check['status']=='unavailable':
        warnings.append('이번 SEC 신규 보고서 확인이 실패했습니다. 마지막 검증된 보고 수량으로 시장 가격만 갱신했습니다.')
    sources = [{'type':'공식 공시','title':'국민연금 기금운용 현황','url':config['sources'][0]['url'],
                'detail':f"{start} 기준 · {base.get('publishedAt')} 발표"},
               {'type':'공식 보고','title':'국민연금 SEC 13F','url':config['filing']['sourceFilingUrl'],
                'detail':f"{config['filing']['reportDate']} 보유분 · {config['filing']['filedDate']} 제출"},
               *[{'type':'시장 관측','title':f'{symbol} · {c.get("name",symbol)}','url':c['sourceUrl'],
                  'detail':f'{start} → {market_date} 같은 제공자의 일별 종가/조정종가'} for symbol,c in core.items()],
               *[{**s, **({'detail':f'대체: 연 6% × {days}/365 + 해외주식 수익률 × 0.25'} if s.get('type')=='모형 가정' else {})} for s in config['sources'] if s.get('type') in ('공식 목표','보도·가정','공식+가정','모형 가정')]]
    summary = {'schemaVersion':1,'snapshotVersion':version,'generatedAt':generated_at,'marketDate':market_date,
               'baseline':base,'inputs':inputs,'assetBaseline':assets,'result':calculate(inputs,assets),
               'sensitivity':sensitivity(inputs,assets),
               'filing':{'reportDate':config['filing']['reportDate'],'filedDate':config['filing']['filedDate'],
                         'totalCount':len(rows),'directCount':len(direct),'reportCoveragePct':coverage*100,
                         'overseasCoveragePct':base_krw/base['overseas']*100,'totalValueUSD':total_report,
                         'directReturnPct':direct_return,'residualReturnPct':residual_return,'blendedReturnPct':blended,
                         'base13fKRW':base_krw,'residualBaseKRW':residual,'detailsFile':filename,
                         'sourceFilingUrl':config['filing']['sourceFilingUrl'],
                         'sourceInformationTableUrl':config['filing']['sourceInformationTableUrl'],
                         'checkedAt':latest_check.get('checkedAt',latest_check.get('lastVerifiedAt'))},
               'market':{'date':market_date,'windowDays':days,'observations':observations,
                         'domesticBondMethod':'국채 3년·10년 ETF 50:50 조정종가 수익률',
                         'latestFilingCheck':latest_check},'sources':sources,'warnings':warnings,
               'update':{'frequency':'미국 종가 확인 후 하루 1회 (한국시간 화~토 10:30)',
                         'scheduleUTC':'30 1 * * 2-6','method':'scheduled-close',
                         'baselineRefresh':'새 공식 월별 공시 검증 후 반영',
                         'filingRefresh':'SEC 신규 제출 자동 확인; 보유 명세 매핑 검증 후 반영'}}
    details = {'schemaVersion':1,'snapshotVersion':version,'marketDate':market_date,
               'reportDate':config['filing']['reportDate'],'rows':detail_rows}
    return summary, details


def check_publication(directory):
    """Provider-free release check used by CI and local integration."""
    directory=Path(directory);s=load_json(directory/'summary.json')
    if s.get('schemaVersion')!=1 or s['filing']['detailsFile']!=f"holdings-{s['snapshotVersion']}.json":
        raise ValueError('Unsupported schema or unexpected detail filename')
    if len(s['snapshotVersion'])!=16 or any(c not in '0123456789abcdef' for c in s['snapshotVersion']):
        raise ValueError('Invalid snapshot version')
    d=load_json(directory/s['filing']['detailsFile'])
    if d['snapshotVersion']!=s['snapshotVersion'] or d['marketDate']!=s['marketDate']:
        raise ValueError('Published summary/detail mismatch')
    if len(d['rows'])!=s['filing']['totalCount'] or sum(r['method']=='direct' for r in d['rows'])!=s['filing']['directCount']:
        raise ValueError('Published detail coverage mismatch')
    if not math.isclose(sum(r['reportValueUSD'] for r in d['rows']),s['filing']['totalValueUSD'],abs_tol=.01):
        raise ValueError('Published detail USD total mismatch')
    result=calculate(s['inputs'],s['assetBaseline'])
    for key,value in result.items():
        if isinstance(value,(int,float)) and not math.isclose(value,s['result'][key],rel_tol=1e-10,abs_tol=1e-9):
            raise ValueError(f'Published calculation mismatch: {key}')
    if s['baseline']['date']>=s['marketDate'] or s['market']['date']!=s['marketDate']:
        raise ValueError('Published market chronology invalid')
    return {'snapshotVersion':s['snapshotVersion'],'marketDate':s['marketDate'],
            'weight':s['result']['weight'],'directCount':s['filing']['directCount']}


def publish(summary, details, directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    existing_path = directory/'summary.json'
    if existing_path.exists() and load_json(existing_path)['marketDate'] > summary['marketDate']:
        raise ValueError('Refusing to overwrite newer market snapshot')
    if summary['snapshotVersion'] != details['snapshotVersion'] or summary['marketDate'] != details['marketDate']:
        raise ValueError('Snapshot/detail version or date mismatch')
    # Immutable evidence first, pointer last. Previous versions are retained so a
    # browser which already read an old summary can still open its exact detail.
    for name, data in [(summary['filing']['detailsFile'], details), ('summary.json', summary)]:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=directory,delete=False) as out:
            out.write(canonical(data)+'\n'); temporary = out.name
        os.replace(temporary,directory/name)


def run(args):
    config = load_json(args.config)
    validate_config(config)
    output = Path(args.output_dir)
    if args.check:
        print(canonical(check_publication(output)));return
    cutoff = args.as_of or (dt.datetime.now(UTC).date()-dt.timedelta(days=1)).isoformat()
    if cutoff >= dt.datetime.now(UTC).date().isoformat():
        raise ValueError('Only a fully completed previous UTC day may be used')
    previous = load_json(output/'summary.json') if (output/'summary.json').exists() else None
    if previous and previous['marketDate'] >= cutoff and not args.force:
        print('Preserved existing snapshot: no later completed UTC day requested'); return
    quotes.DEADLINE = time.monotonic()+args.max_seconds
    quotes.ACTION_REVIEWS = config['corporateActions']
    dates = (config['filing']['reportDate'], config['baseline']['date'], cutoff)
    cache = Path(args.cache_dir);cache.mkdir(parents=True,exist_ok=True)
    core = {}
    for symbol in CORE:
        core[symbol] = quotes.read_chart(symbol, dates, cache, refresh=True)
    market_date = common_session(core, cutoff, config['baseline']['date'])
    if previous and previous['marketDate'] >= market_date and not args.force:
        print('Preserved existing snapshot: no newer common completed session');return
    dates = (*dates[:2],market_date)
    # Re-fetch core with strict market-date cutoff if a holiday produced an older
    # common session. No later split/dividend may enter that historical snapshot.
    if market_date != cutoff:
        core = {s:quotes.read_chart(s,dates,cache,refresh=True) for s in CORE}
    latest_check = filing_check(config,quotes.DEADLINE)
    symbols = sorted({quotes.symbol_for(h['ticker']) for h in config['holdings']})
    def fetch(symbol):
        try:
            return symbol,quotes.read_chart(symbol,dates,cache,refresh=True)
        except Exception as error:
            return symbol,{'error':str(error),'valid':False}
    collected = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i,(symbol,chart) in enumerate(pool.map(fetch,symbols),1):
            collected[symbol]=chart
            if i%100==0:print(f'Checked {i}/{len(symbols)} report symbols',flush=True)
    rows = [quotes.price_holding(h,collected.get(quotes.symbol_for(h['ticker'])),dates,.005) for h in config['holdings']]
    previous_details = load_json(output/previous['filing']['detailsFile']) if previous else None
    quality_gate(rows,config,previous_details)
    if time.monotonic() > quotes.DEADLINE:
        raise TimeoutError('Collection exceeded bounded budget; preserved publication')
    summary,details=build_snapshot(config,core,rows,market_date,latest_check,dt.datetime.now(UTC).isoformat())
    publish(summary,details,output)
    print(canonical({'snapshotVersion':summary['snapshotVersion'],'marketDate':market_date,
                     'weight':summary['result']['weight'],'directCount':summary['filing']['directCount'],
                     'latestFilingCheck':latest_check['status']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(CONFIG))
    parser.add_argument('--output-dir',default=str(ROOT/'static/data/nps'))
    parser.add_argument('--cache-dir',default=str(Path(tempfile.gettempdir())/'chartview-nps-quotes'))
    parser.add_argument('--max-seconds',type=int,default=600)
    parser.add_argument('--workers',type=int,choices=range(1,5),default=4)
    parser.add_argument('--as-of',help='Latest permitted completed market date YYYY-MM-DD')
    parser.add_argument('--check',action='store_true',help='Validate published files offline without provider calls')
    parser.add_argument('--force',action='store_true',help='Recheck an existing same-date snapshot')
    arguments=parser.parse_args()
    if not 30<=arguments.max_seconds<=1200:parser.error('--max-seconds must be 30..1200')
    try:run(arguments)
    except Exception as error:
        print(f'NPS publication preserved: {error}',file=sys.stderr);sys.exit(1)
