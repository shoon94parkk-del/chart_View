from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v39_visual_asset_is_loaded_and_versioned():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "/static/css/home_visual_v39.css?v=20260913v39" in boot
    assert "homeVisualV39" in boot
    assert "home.dataset.visualVersion = 'v39'" in boot


def test_v39_has_distinct_home_hierarchy_and_mobile_rules():
    css = (ROOT / "static/css/home_visual_v39.css").read_text(encoding="utf-8")
    assert "#home-market-v9.home-market-v9" in css
    assert "#home-watchlist-v30.home-watchlist-v30" in css
    assert "#home-personal-news-v37.home-personal-news-v38" in css
    assert ".news-v38-card.is-lead" in css
    assert "linear-gradient" in css
    assert "@media (max-width: 720px)" in css
    assert "@media (max-width: 390px)" in css
    assert "grid-template-columns: repeat(2,minmax(0,1fr))" in css
    assert "grid-template-columns: 1fr" in css
    assert "@media (prefers-color-scheme: dark)" in css


def test_v39_keeps_existing_home_order_and_news_version():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "market-watchlist-news-body-status" in boot
    assert "home.dataset.newsVersion = 'v38'" in boot
