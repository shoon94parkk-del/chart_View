import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "templates/index.html").read_text(encoding="utf-8")
BOOT = (ROOT / "static/js/chartview_boot_bundle.js").read_text(encoding="utf-8")
BOOT_CSS = (ROOT / "static/css/chartview_boot_bundle.css").read_text(encoding="utf-8")
BUILD = (ROOT / "scripts/build_boot_bundle.py").read_text(encoding="utf-8")


def test_original_page_loads_one_versioned_javascript_boot_request():
    srcs = re.findall(r'<script[^>]+src="(/static/js/[^"]+)"', HTML)
    assert len(srcs) == 1, srcs
    assert srcs[0].startswith("/static/js/chartview_boot_bundle.js?v=")


def test_original_page_loads_one_versioned_stylesheet_boot_request():
    hrefs = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="(/static/css/[^"]+)"', HTML)
    assert len(hrefs) == 1, hrefs
    assert hrefs[0].startswith("/static/css/chartview_boot_bundle.css?v=")


def test_boot_bundle_preserves_generated_version_sentinels_without_loading_them():
    assert 'data-chartview-release-bundle-version="/static/js/chartview_release_bundle.js?v=' in HTML
    assert 'data-chartview-release-css-version="/static/css/chartview_release_bundle.css?v=' in HTML
    assert 'data-ai-daily-widget-version="/static/js/ai_daily_widget.js?v=' in HTML
    assert '<script defer src="/static/js/chartview_release_bundle.js' not in HTML
    assert '<script defer src="/static/js/ai_daily_widget.js' not in HTML
    assert '<link rel="stylesheet" href="/static/css/chartview_release_bundle.css' not in HTML


def test_boot_bundle_contains_every_legacy_script_once():
    paths = re.findall(r'"(static/js/[^"]+\.js)"', BUILD.split("BOOT_SCRIPTS =", 1)[1].split("]", 1)[0])
    assert len(paths) >= 18
    for path in paths:
        marker = f"/* --- {path} --- */"
        assert BOOT.count(marker) == 1, path


def test_boot_css_contains_every_initial_style_once():
    paths = re.findall(r'"(static/css/[^"]+\.css)"', BUILD.split("BOOT_STYLES =", 1)[1].split("]", 1)[0])
    assert len(paths) == 8
    for path in paths:
        marker = f"/* --- {path} --- */"
        assert BOOT_CSS.count(marker) == 1, path


def test_revisit_boot_executes_before_deferred_legacy_scripts():
    revisit = BOOT.index("/* --- static/js/p2_revisit_v1.js --- */")
    chart = BOOT.index("/* --- static/js/chart.js --- */")
    assert revisit < chart


def test_bundled_optional_helpers_do_not_reload_themselves():
    promo = (ROOT / "static/js/promo_v1.js").read_text(encoding="utf-8")
    continuity = (ROOT / "static/js/ui_continuity_v53.js").read_text(encoding="utf-8")
    assert "if (window.__CHARTVIEW_BOOT_BUNDLE__)" in promo
    assert "if (window.__CHARTVIEW_BOOT_BUNDLE__) return;" in continuity
    assert BOOT.index("/* --- static/js/home_summary_v54.js --- */") < BOOT.index("/* --- static/js/ui_continuity_v53.js --- */")
    ai = (ROOT / "static/js/ai_daily_widget.js").read_text(encoding="utf-8")
    assert "function openLedgerWhenReady(attempt=0)" in ai
    assert "if(attempt<40)setTimeout(()=>openLedgerWhenReady(attempt+1),120)" in ai
