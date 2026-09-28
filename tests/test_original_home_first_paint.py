from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "static/js/home_brief_v8.js").read_text(encoding="utf-8")
HEATMAP = (ROOT / "static/js/home_heatmap_v57.js").read_text(encoding="utf-8")
PROFILE = (ROOT / "static/js/profile_sync_v1.js").read_text(encoding="utf-8")
AI = (ROOT / "static/js/ai_daily_widget.js").read_text(encoding="utf-8")
UX = (ROOT / "static/js/ux_patterns_v12.js").read_text(encoding="utf-8")
NEWS = (ROOT / "static/js/personalized_news_v40.js").read_text(encoding="utf-8")
WATCH = (ROOT / "static/js/watchlist_v30.js").read_text(encoding="utf-8")
QUICK = (ROOT / "static/js/watchlist_quick_add_v48.js").read_text(encoding="utf-8")


def test_home_and_heatmap_share_snapshot_cache():
    assert "chartview-home-snapshot-v18" in HOME
    assert "chartview-home-snapshot-v18" in HEATMAP
    assert "localStorage.getItem('chartview-home-snapshot-v17')" in HOME  # one-time migration


def test_heatmap_geometry_has_real_first_paint_grace():
    assert "scheduleRefresh(3200);" in HEATMAP
    start = HEATMAP[HEATMAP.index("function start()"):]
    assert "window.requestIdleCallback" not in start.split("const observer", 1)[0]
    assert "refreshServerLive(false);" in HEATMAP


def test_noncritical_home_features_use_explicit_grace():
    assert "scheduleInit(8000)" in PROFILE
    assert "data-app-mode=\"watchlist\"" in PROFILE
    assert "requestIdleCallback" not in PROFILE[PROFILE.index("let initScheduled"):]

    assert "setTimeout(run, force ? 700 : 3200);" in UX
    assert "requestIdleCallback" not in UX[UX.index("function scheduleDataStatus"):UX.index("function boot()")]

    assert "setTimeout(run,2600);" in AI
    assert "if(!event.persisted)return;" in AI

    assert "setTimeout(observe, 2600);" in NEWS
    assert "rootMargin: '100px 0px'" in NEWS


def test_hidden_watchlist_does_not_fetch_quotes_on_home_boot():
    init = WATCH[WATCH.index("function init()"):]
    assert "setTimeout(refreshCurrentQuotesQuietly, 0);" not in init
    assert "setTimeout(refreshCurrentQuotesQuietly, 2200);" in init
    assert "refreshCurrentQuotesQuietly();" in WATCH[WATCH.index("function refreshWatchlistOnEntry()"):WATCH.index("async function loadQuotes")]

    wrap = QUICK[QUICK.index("function wrapWatchlistRender"):QUICK.index("function attachObserver")]
    assert "watchlist-tab" in wrap
    assert "classList.contains('active')" in wrap


def test_ai_pick_stays_lazy_on_home_but_supports_explicit_deep_link():
    assert "function isLedgerDeepLink()" in AI
    assert "params.get('tab')==='screener'&&params.get('view')==='ai-picks'" in AI
    assert "if(isLedgerDeepLink())setTimeout(()=>openLedgerWhenReady(),80);" in AI
    assert "window.__openPickManagement" in AI
    click_region = AI[AI.index("document.addEventListener('click'"):AI.index("function scheduleMount")]
    assert "installAiLedgerAssets()" not in click_region
