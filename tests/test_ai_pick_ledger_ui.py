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


def test_ai_pick_deep_link_is_not_overridden_by_initial_home_boot():
    js = read("static/js/home_watchlist_boot_v32c.js")
    assert "wantsAiPickLedger" in js
    assert "params.get('tab') === 'screener'" in js
    assert "params.get('view') === 'ai-picks'" in js
    assert "if (wantsAiPickLedger())" in js


def test_pick_view_retries_until_shell_exists_and_uses_app_navigation():
    js = read("static/js/ai_pick_ledger_v52.js")
    compact = js.replace(" ", "")
    assert "functionopenView(view,attempt=0)" in compact
    assert "setTimeout(()=>openView(view,attempt+1),100)" in compact
    assert "window.__openAppTab('screener')" in js


def test_home_pick_mobile_layout_has_named_grid_areas_and_nonwrapping_score_badge():
    js = read("static/js/ai_daily_widget.js")
    compact = js.replace(" ", "")
    assert "grid-template-areas" in js
    assert "grid-area:name" in compact
    assert "grid-area:score" in compact
    assert "white-space:nowrap" in compact


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
