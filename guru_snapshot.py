"""Dated results and evidence: one immutable version, atomic publication."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

from guru_financials import classify_company
from guru_rules import CRITERIA_VERSION, evaluate_company, finite
from guru_extensions import STRATEGIES, evaluate_extension, technical_metrics, relative_strength


def build_snapshot(universe: list[dict], prices: dict, financials: dict, *, generated_at: str, market=None, quarters=None) -> tuple[dict, dict]:
    trade_date = prices.get('tradeDate')
    if not trade_date:
        raise ValueError('Missing validated trade date')
    quotes = {r['symbol']: dict(r, currency='KRW') for r in prices.get('stocks', []) if r.get('date') == trade_date}
    companies, strategies = {}, {}
    unique = {r['symbol']: r for r in universe}
    technical = {}
    market_rows = (market or {}).get('companies') or {}
    # A relative-return cohort needs a verified close on the same trading date.
    # Missing/stale quotes remain insufficient in the FULL screening universe.
    eligible_count = sum(classify_company(r)['status']=='supported' and s in quotes
                         and finite(quotes[s].get('price')) and quotes[s]['price']>0 for s,r in unique.items())
    for symbol, identity in unique.items():
        if classify_company(identity)['status']!='supported': continue
        quote=quotes.get(symbol)
        value=technical_metrics((market_rows.get(symbol) or {}).get('bars'),trade_date)
        if value and quote and finite(quote.get('price')) and quote['price']>0 and abs(value['price']/quote['price']-1)<=.001: technical[symbol]=value
    relative_strength(technical,eligible_count)
    for strategy in STRATEGIES:
        counts = {k+'Count': 0 for k in ('unsupported', 'pending', 'insufficient', 'failed', 'matched')}
        results = []
        reasons = {}
        for symbol, identity in unique.items():
            raw = (financials.get('companies') or {}).get(symbol)
            company = dict(raw or {'symbol': symbol, 'collection': {'status': 'pending'}})
            company['classification'] = classify_company(identity)
            evaluation = (evaluate_company(company, quotes.get(symbol), strategy=strategy) if strategy in {'buffett','lynch'} else
                evaluate_extension(company,quotes.get(symbol),strategy=strategy,technical=technical.get(symbol),
                    quarter=((quarters or {}).get('companies') or {}).get(symbol)))
            counts[evaluation['status']+'Count'] += 1
            for reason in evaluation['reasons']:
                if evaluation['status'] in {'insufficient','unsupported'}: reasons[reason] = reasons.get(reason,0)+1
            if evaluation['status'] != 'matched': continue
            results.append({'symbol': symbol, 'name': identity.get('name') or symbol, 'market': identity.get('market'),
                            'tradeDate': trade_date, 'annualReportYear': company.get('annualReportYear'),
                            'metrics': evaluation['metrics'], 'checks': evaluation['checks'],
                            'basis': evaluation.get('basis'), 'evidenceKey': symbol})
            evidence = companies.setdefault(symbol, {'symbol': symbol, 'name': identity.get('name') or symbol,
                'basis': company.get('basis'), 'currency': company.get('currency'), 'annual': company.get('annual', []),
                'sources': company.get('sources', {}), 'epsComparability': company.get('epsComparability'),
                'quarter': ((quarters or {}).get('companies') or {}).get(symbol),
                'technical': technical.get(symbol), 'dailyBars': (market_rows.get(symbol) or {}).get('bars'),
                'checkedAt': company.get('checkedAt'), 'strategies': {}})
            evidence['strategies'][strategy] = evaluation
        if strategy=='greenblatt':
            results.sort(key=lambda r:(r['metrics']['annualPE'],r['symbol']))
            for i,row in enumerate(results,1):
                row['metrics']['valueRank']=i
            excluded=results[30:]; results=results[:30]
            counts['matchedCount']-=len(excluded); counts['failedCount']+=len(excluded)
            for row in excluded:
                evidence=companies[row['symbol']]; evidence['strategies'].pop(strategy)
                if not evidence['strategies']: del companies[row['symbol']]
        else: results.sort(key=lambda r: (r['name'], r['symbol']))
        strategies[strategy] = {**counts, 'universeCount': len(unique), 'evaluatedCount': counts['matchedCount']+counts['failedCount'],
                                'results': results, 'missingReasons': reasons}
    checks = [r['checkedAt'] for r in (financials.get('companies') or {}).values() if r.get('checkedAt')]
    snapshot = {'schemaVersion': 1, 'criteriaVersion': CRITERIA_VERSION, 'generatedAt': generated_at,
                'tradeDate': trade_date, 'financialAsOf': min(checks) if checks else generated_at,
                'financialCheckedThrough': max(checks) if checks else generated_at,
                'source': 'OpenDART annual and single-quarter financial statements · KIND universe · Yahoo dated OHLCV',
                'marketCoverage': {'eligibleCount':eligible_count,'observedCount':len(technical),'cohort':'KIND supported ordinary companies with verified same-date positive closes','relativeStrengthMethod':'252-session return midrank percentile; not IBD RS Rating'},
                'collection': financials.get('collection', {'status': 'pending'}), 'strategies': strategies}
    snapshot['extensionCollection']={'market':(market or {}).get('collection',{'status':'pending'}),
                                     'quarters':(quarters or {}).get('collection',{'status':'pending'})}
    version_content = {'tradeDate': trade_date, 'criteriaVersion': CRITERIA_VERSION, 'strategies': strategies, 'companies': companies}
    version = hashlib.sha256(json.dumps(version_content, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()[:20]
    snapshot['snapshotVersion'] = version
    return snapshot, {'snapshotVersion': version, 'criteriaVersion': CRITERIA_VERSION, 'tradeDate': trade_date, 'companies': companies}


def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n'
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(raw, encoding='utf-8')
    os.replace(temporary, path)


def publish_snapshot(snapshot: dict, evidence: dict, directory: Path) -> None:
    if snapshot.get('snapshotVersion') != evidence.get('snapshotVersion'):
        raise ValueError('Evidence version mismatch')
    for strategy in snapshot['strategies'].values():
        if (strategy['universeCount'] != sum(strategy[k+'Count'] for k in ('unsupported','pending','insufficient','failed','matched'))
            or strategy['evaluatedCount'] != strategy['matchedCount']+strategy['failedCount']
            or strategy['matchedCount'] != len(strategy['results'])):
            raise ValueError('Invalid coverage counts')
        if any(row['symbol'] not in evidence['companies'] for row in strategy['results']):
            raise ValueError('Missing candidate evidence')
    # Validate serialization before replacing any known-good file.
    json.dumps([snapshot, evidence], allow_nan=False)
    atomic_json(directory/'guru_evidence.json', evidence)
    atomic_json(directory/'guru_screening.json', snapshot)
