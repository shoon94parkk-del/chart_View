from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v391_visual_asset_is_loaded_under_release_ui():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "/static/css/home_visual_v39_1.css?v=20260913v391" in boot
    assert "data-home-visual-v391" in boot
    assert "home.dataset.visualVersion = 'v39'" in boot
    assert "home.dataset.uiVersion = 'v40-stage12'" in boot


def test_v391_news_range_visual_and_watchlist_emphasis_are_preserved():
    css = (ROOT / "static/css/home_visual_v39_1.css").read_text(encoding="utf-8")
    assert 'content: "5D · 최근 5거래일"' in css
    assert ".home-watch-v33-quote b" in css
    assert ".home-watch-v33-quote em.up" in css
    assert ".home-watch-v33-quote em.down" in css
    assert ":has(.home-watch-v33-quote em.up)" in css
    assert "@media (max-width: 720px)" in css
    assert "@media (max-width: 390px)" in css
    assert "@media (prefers-color-scheme: dark)" in css


def test_v40_keeps_five_trading_day_news_market_context():
    js = (ROOT / "static/js/personalized_news_v40.js").read_text(encoding="utf-8")
    assert "period=5d" in js
    assert "5거래일 가격 흐름" in js
