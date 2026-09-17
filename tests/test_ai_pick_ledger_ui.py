from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ai_daily_widget_loads_ai_pick_ledger_assets():
    js = read("static/js/ai_daily_widget.js")
    assert "/static/css/ai_pick_ledger_v52.css" in js
    assert "/static/js/ai_pick_ledger_v52.js" in js


def test_home_ai_pick_link_opens_discovery_ledger():
    js = read("static/js/ai_daily_widget.js")
    assert '/?tab=screener&view=ai-picks' in js
    assert '전체 기록 →' in js


def test_ledger_module_contains_dense_discovery_contract_without_rank_column():
    js = read("static/js/ai_pick_ledger_v52.js")
    assert 'data-discovery-view="screener"' in js
    assert 'data-discovery-view="ai-picks"' in js
    assert 'const PAGE_SIZE = 60' in js
    for label in ("추천일", "종목", "추천가", "현재가", "수익률", "최고수익률", "점수"):
        assert label in js
    assert 'data-label="순위"' not in js
    assert '<span>순위</span>' not in js
    assert 'ledger-rank' not in js
    assert 'window.__openAiPickLedger' in js
    assert "view') === 'ai-picks'" in js


def test_ledger_css_has_mobile_compact_mode_without_rank_column():
    css = read("static/css/ai_pick_ledger_v52.css")
    assert "@media(max-width:700px)" in css.replace(" ", "")
    assert ".ai-ledger-row" in css
    assert "overflow-x:hidden" in css.replace(" ", "")
    assert ".ledger-rank" not in css


def test_legacy_recommendations_page_redirects_to_ledger():
    html = read("static/recommendations.html")
    assert '/?tab=screener&view=ai-picks' in html
    assert 'location.replace' in html
