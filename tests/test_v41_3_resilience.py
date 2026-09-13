from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_resilience_assets_are_loaded():
    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    assert 'resilience_v41_3.css?v=' in boot
    assert 'resilience_v41_3.js?v=' in boot


def test_resilience_is_state_driven_and_hardens_links():
    js = (ROOT / 'static/js/resilience_v41_3.js').read_text(encoding='utf-8')
    hub = (ROOT / 'static/js/my_hub_v41.js').read_text(encoding='utf-8')
    assert "u.protocol === 'https:' || u.protocol === 'http:'" in js
    assert 'aria-busy' in js
    assert 'aria-pressed' in js
    assert '마지막 수신' in js
    assert 'chartview:v41-news-state' in js
    assert 'MutationObserver' not in js
    assert 'feedSnapshot' not in js
    assert 'receivedAt' in hub and 'lastError' in hub and 'isStale' in hub
    assert '기존 뉴스는 그대로 유지합니다.' in hub


def test_resilience_accessibility_and_dark_mode():
    css = (ROOT / 'static/css/resilience_v41_3.css').read_text(encoding='utf-8')
    assert ':focus-visible' in css
    assert 'prefers-color-scheme:dark' in css
    assert 'prefers-reduced-motion:reduce' in css
