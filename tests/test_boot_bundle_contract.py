import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "templates/index.html").read_text(encoding="utf-8")
BOOT = (ROOT / "static/js/chartview_boot_bundle.js").read_text(encoding="utf-8")
BUILD = (ROOT / "scripts/build_boot_bundle.py").read_text(encoding="utf-8")


def test_original_page_loads_one_versioned_javascript_boot_request():
    srcs = re.findall(r'<script[^>]+src="(/static/js/[^"]+)"', HTML)
    assert len(srcs) == 1, srcs
    assert srcs[0].startswith("/static/js/chartview_boot_bundle.js?v=")


def test_boot_bundle_preserves_generated_version_sentinels_without_loading_them():
    assert 'data-chartview-release-bundle-version="/static/js/chartview_release_bundle.js?v=' in HTML
    assert 'data-ai-daily-widget-version="/static/js/ai_daily_widget.js?v=' in HTML
    assert '<script defer src="/static/js/chartview_release_bundle.js' not in HTML
    assert '<script defer src="/static/js/ai_daily_widget.js' not in HTML


def test_boot_bundle_contains_every_legacy_entry_once():
    paths = re.findall(r'"(static/js/[^"]+\.js)"', BUILD.split("BOOT_SCRIPTS =", 1)[1].split("]", 1)[0])
    assert len(paths) >= 17
    for path in paths:
        marker = f"/* --- {path} --- */"
        assert BOOT.count(marker) == 1, path


def test_revisit_boot_executes_before_deferred_legacy_scripts():
    revisit = BOOT.index("/* --- static/js/p2_revisit_v1.js --- */")
    chart = BOOT.index("/* --- static/js/chart.js --- */")
    assert revisit < chart
