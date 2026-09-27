from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "static/js/home_brief_v8.js").read_text(encoding="utf-8")
HEATMAP = (ROOT / "static/js/home_heatmap_v57.js").read_text(encoding="utf-8")
PROFILE = (ROOT / "static/js/profile_sync_v1.js").read_text(encoding="utf-8")
AI = (ROOT / "static/js/ai_daily_widget.js").read_text(encoding="utf-8")
UX = (ROOT / "static/js/ux_patterns_v12.js").read_text(encoding="utf-8")


def test_home_and_heatmap_share_snapshot_cache():
    assert "chartview-home-snapshot-v18" in HOME
    assert "chartview-home-snapshot-v18" in HEATMAP
    assert "localStorage.getItem('chartview-home-snapshot-v17')" in HOME  # one-time migration


def test_heatmap_geometry_is_deferred_and_live_refresh_not_forced_twice():
    assert "function scheduleRefresh(delay = 1400)" in HEATMAP
    assert "requestIdleCallback" in HEATMAP
    assert "refreshServerLive(false);" in HEATMAP


def test_noncritical_home_features_wait_until_after_first_paint():
    assert "function scheduleInit()" in PROFILE
    assert "requestIdleCallback" in PROFILE
    assert "function scheduleDataStatus(force = false)" in UX
    boot = UX[UX.index("function boot()"):]
    assert "installDataStatus();" not in boot.split("document.addEventListener('click'", 1)[0]


def test_ai_pick_stays_lazy_on_home_but_supports_explicit_deep_link():
    assert "if(!event.persisted)return;" in AI
    assert "function isLedgerDeepLink()" in AI
    assert "params.get('tab')==='screener'&&params.get('view')==='ai-picks'" in AI
    assert "if(isLedgerDeepLink())installAiLedgerAssets();" in AI
