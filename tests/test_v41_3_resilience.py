from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v413_assets_are_loaded():
    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    assert 'resilience_v41_3.css?v=20260913v413' in boot
    assert 'resilience_v41_3.js?v=20260913v413' in boot
    assert "home.dataset.resilienceVersion = 'v41.3'" in boot


def test_v413_preserves_feed_and_hardens_links():
    js = (ROOT / 'static/js/resilience_v41_3.js').read_text(encoding='utf-8')
    assert "기존 뉴스를 계속 표시합니다" in js
    assert "u.protocol === 'https:' || u.protocol === 'http:'" in js
    assert "aria-busy" in js
    assert "aria-pressed" in js
    assert "마지막 갱신" in js


def test_v413_accessibility_and_dark_mode():
    css = (ROOT / 'static/css/resilience_v41_3.css').read_text(encoding='utf-8')
    assert ':focus-visible' in css
    assert 'prefers-color-scheme:dark' in css
    assert 'prefers-reduced-motion:reduce' in css
