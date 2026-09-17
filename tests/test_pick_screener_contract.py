import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'static' / 'data'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def test_pick_ledger_contains_latest_daily_pick():
    daily = load('ai_daily_rankings.json')
    recs = load('ai_recommendations.json')
    latest = max(d['tradeDate'] for d in daily['days'])
    latest_codes = {x['code'] for d in daily['days'] if d['tradeDate'] == latest for x in d['top3']}
    ledger_codes = {x['code'] for x in recs['recommendations'] if x['recommendedDate'] == latest}
    assert latest_codes == ledger_codes


def test_pick_prices_are_not_older_than_screener_trade_date():
    screener = load('screener_meta.json')['tradeDate']
    recs = load('ai_recommendations.json')['recommendations']
    assert all(str(x.get('lastUpdatedTradeDate') or '') >= screener for x in recs)


def test_screener_display_source_matches_meta_date():
    meta = load('screener_meta.json')
    screen = load('screener.json')
    assert screen.get('tradeDate') == meta.get('tradeDate')
