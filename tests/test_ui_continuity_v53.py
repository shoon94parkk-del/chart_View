from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_app_loads_shared_ui_continuity_layer():
    html = read("templates/index.html")
    assert "/static/css/ui_continuity_v53.css?v=20260916v53" in html


def test_pick_naming_reflects_human_final_selection():
    home = read("static/js/ai_daily_widget.js")
    ledger = read("static/js/ai_pick_ledger_v52.js")
    assert "ChartView PICK 3" in home
    assert "ChartView AI PICK 3" not in home
    assert ">PICK 기록<" in ledger
    assert "CHARTVIEW PICK" in ledger
    assert "AI 스크리닝 · 최종 선정" in ledger


def test_shared_ui_tokens_cover_primary_app_surfaces():
    css = read("static/css/ui_continuity_v53.css")
    for token in (
        "--cv-page-gutter",
        "--cv-card-radius",
        "--cv-control-radius",
        "--cv-section-gap",
        "--cv-border",
        "--cv-surface",
    ):
        assert token in css
    for surface in (
        "#home-tab",
        "#watchlist-tab",
        "#chart-tab",
        "#fwdper-tab",
        "#screener-tab",
        "#macro-tab",
        ".revision-gap-panel",
        ".ai-ledger-panel",
    ):
        assert surface in css


def test_mobile_continuity_reduces_box_density_and_preserves_safe_area():
    css = read("static/css/ui_continuity_v53.css").replace(" ", "")
    assert "@media(max-width:720px)" in css
    assert "padding-bottom:calc(" in css
    assert "env(safe-area-inset-bottom)" in css
    assert ".ai-ledger-kpis" in css
    assert ".ai-ledger-tools" in css
    assert ".revision-gap-card" in css
