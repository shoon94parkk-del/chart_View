from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v392_visual_asset_is_preserved_under_release_ui():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "/static/css/ui_polish_v39_2.css?v=20260913v392" in boot
    assert "data-ui-polish-v392" in boot
    assert "home.dataset.uiVersion = 'v40-stage12'" in boot
    assert "home.dataset.visualVersion = 'v39'" in boot


def test_v392_unifies_global_surfaces_and_mobile_touch_targets():
    css = (ROOT / "static/css/ui_polish_v39_2.css").read_text(encoding="utf-8")
    assert ".header.app-utility-header #unified-input" in css
    assert ".tab-nav" in css
    assert ".app-bottom-nav" in css
    assert ".date-section" in css
    assert ".chart-section" in css
    assert ".metric-section" in css
    assert ".per-section" in css
    assert ".macro-section" in css
    assert "min-height: 44px" in css
    assert "@media (max-width: 720px)" in css
    assert "@media (max-width: 390px)" in css
    assert "@media (prefers-color-scheme: dark)" in css


def test_release_keeps_home_order_and_v39_visual_contract():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "market-watchlist-news-body-status" in boot
    assert "home.dataset.newsVersion = 'v40'" in boot
    assert "home.dataset.visualVersion = 'v39'" in boot
    assert "/static/css/release_ui_v40.css" in boot
    assert "/static/css/comparison_ui_v40.css" in boot
