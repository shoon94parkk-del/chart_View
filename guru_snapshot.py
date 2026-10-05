"""Dated results and evidence: one immutable version, atomic publication."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

from guru_financials import classify_company
from guru_rules import CRITERIA_VERSION, evaluate_company


def build_snapshot(universe: list[dict], prices: dict, financials: dict, *, generated_at: str) -> tuple[dict, dict]:
    trade_date = prices.get('tradeDate')
    if not trade_date:
        raise ValueError('Missing validated trade date')
    quotes = {r['symbol']: dict(r, currency='KRW') for r in prices.get('stocks', []) if r.get('date') == trade_date}
    companies, strategies = {}, {}
    unique = {r['symbol']: r for r in universe}
    for strategy in ('buffett', 'lynch'):
        counts = {k+'Count': 0 for k in ('unsupported', 'pending', 'insufficient', 'failed', 'matched')}
        results = []
        reasons = {}
        for symbol, identity in unique.items():
            raw = (financials.get('companies') or {}).get(symbol)
            company = dict(raw or {'symbol': symbol, 'collection': {'status': 'pending'}})
            company['classification'] = (raw or {}).get('classification') or classify_company(identity)
            evaluation = evaluate_company(company, quotes.get(symbol), strategy=strategy)
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
                'checkedAt': company.get('checkedAt'), 'strategies': {}})
            evidence['strategies'][strategy] = evaluation
        results.sort(key=lambda r: (r['name'], r['symbol']))
        strategies[strategy] = {**counts, 'universeCount': len(unique), 'evaluatedCount': counts['matchedCount']+counts['failedCount'],
                                'results': results, 'missingReasons': reasons}
    snapshot = {'schemaVersion': 1, 'criteriaVersion': CRITERIA_VERSION, 'generatedAt': generated_at,
                'tradeDate': trade_date, 'financialAsOf': financials.get('generatedAt') or generated_at,
                'source': 'OpenDART annual financial statements · KIND universe · Yahoo dated closing prices',
                'collection': financials.get('collection', {'status': 'pending'}), 'strategies': strategies}
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
