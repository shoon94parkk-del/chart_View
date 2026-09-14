from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_first_paint_gate_waits_for_real_home_ready():
    css = (ROOT / "static/css/ux_patch.css").read_text(encoding="utf-8")
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/index.html").read_text(encoding="utf-8")

    # The legacy server markup is analysis-first, so first paint must be gated
    # until Home is dynamically installed and selected.
    assert 'id="chart-tab" class="tab-content active"' in template
    assert "body.app-booting:not(.cv-home-ready) #app" in css
    assert "visibility:hidden!important" in css

    # Regression: the old two-second fail-open marked Home ready even when Home
    # did not exist, exposing the chart for a few seconds before navigation.
    assert "attempt < 160" in boot
    assert "attempt < 40" not in boot
    assert "document.body.classList.add('cv-home-ready');" not in boot
    assert "body.app-booting:not(.cv-home-ready) #app" in boot
    assert "if (!userChangedView && document.getElementById('home-tab'))" in boot
    assert "document.addEventListener('click', markUserNavigation, true)" in boot
    assert "event.isTrusted" in boot
