from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_initial_route_and_scroll_have_one_owner():
    nav = read("static/js/ux_v3.js")
    boot = read("static/js/home_watchlist_boot_v32c.js")
    assert "function resolveInitialRoute()" in nav
    assert "function applyInitialRoute(route, attempt = 0)" in nav
    assert "attempt < 160" in nav
    assert "history.scrollRestoration = 'manual'" in nav
    assert "function rememberCurrentScroll()" in nav
    assert "function restoreScroll(" in nav
    assert "__openAppTab('home'" not in boot


def test_chart_cache_has_ttl_and_bounded_idle_prefetch():
    js = read("static/js/chart.js")
    assert "CHART_CACHE_TTL = 5 * 60 * 1000" in js
    assert "CHART_PREFETCH_CONCURRENCY = 2" in js
    assert "requestIdleCallback" in js
    assert "chartLoadSeq decides which response is allowed to paint" in js
    assert "새 데이터 갱신에 실패했습니다. 표시 중인 차트는 유지했습니다." in js


def test_hidden_chart_is_not_loaded_by_state_or_watchlist_boot():
    state = read("static/js/app_state_v40.js")
    watch = read("static/js/watchlist_v30.js")
    chart = read("static/js/chart.js")
    nav = read("static/js/ux_v3.js")
    condition = "document.getElementById('chart-tab')?.classList.contains('active')"
    assert condition in state
    assert condition in watch
    assert "chartTab?.classList.contains('active')" in chart
    assert "document.body.classList.contains('app-booting')" in chart
    assert "typeof window.__ensureChartVisible === 'function'" in nav


def test_home_watchlist_basis_uses_existing_quote_cache():
    js = read("static/js/release_ui_v40.js")
    block = js.split("function readWatchlistQuoteCache()", 1)[1].split("function observeHomeWatchlist()", 1)[0]
    assert "chartview-watchlist-quotes-v33" in block
    assert "/api/compare" not in block
    assert "quote.tradeDate" in block


def test_home_order_prioritizes_watchlist_before_pick_and_news():
    js = read("static/js/home_watchlist_boot_v32c.js")
    assert "[body, watchlist, aiTop3, news, status]" in js
    assert "market-body-watchlist-ai-top3-news-status" in js


def test_home_only_modules_are_scoped_away_from_analysis():
    css = read("static/css/ux_patch.css")
    assert "#chart-tab #home-market-v9" in css
    assert "#chart-tab #home-personal-news-v37" in css
    assert "min-height:132px" in css
    assert '#chart-tab .chart-unit[data-stale="true"]' in css


def test_home_news_prefers_direct_relations():
    js = read("static/js/personalized_news_v40.js")
    block = js.split("function pickDiverse", 1)[1].split("function renderArticles", 1)[0]
    assert "relationType === 'direct'" in block
    assert "directB - directA" in block



def test_chart_asset_key_tracks_hidden_loading_guard():
    html = read("templates/index.html")
    assert "/static/js/chart.js?v=20260921p1a03" in html



def test_desktop_chart_periods_do_not_wrap():
    css = read("static/css/comparison_ui_v40.css")
    block = css.split("#chart-tab .v40-chart-periods {", 1)[1].split("}", 1)[0]
    quick = css.split("#chart-tab .v40-chart-periods .quick-periods", 1)[1].split("}", 1)[0]
    assert "flex-wrap: nowrap" in block
    assert "flex-wrap: nowrap" in quick



def test_clean_root_does_not_restore_previous_history_tab():
    nav = read("static/js/ux_v3.js")
    block = nav.split("function resolveInitialRoute()", 1)[1].split("function cleanRouteUrl()", 1)[0]
    assert "const state = history.state" not in block
    assert "state?.chartView" not in block
    assert "return { tab: 'home'" in block
    assert "event.state?.chartView" in nav.split("window.addEventListener('popstate'", 1)[1]


def test_discover_bottom_nav_is_deterministic_and_top_first():
    nav = read("static/js/ux_v3.js")
    block = nav.split("bottom.querySelectorAll('[data-app-mode]')", 1)[1].split("document.body.classList.add('app-shell-ready')", 1)[0]
    assert "mode === 'discover' ? 'screener'" in block
    assert "scroller.scrollTop = 0" in block
    assert "document.scrollingElement || document.documentElement" in block
    assert "window.__openScreenerDiscoveryView?.()" in block
    assert "[40, 100, 220].forEach((delay) => setTimeout(jumpDiscoverTop, delay))" in block
    assert "mode === 'discover' ? 'screener'" in block


def test_screener_opens_top_first_and_has_one_tap_top_control():
    nav = read("static/js/ux_v3.js")
    js = read("static/js/screener.js")
    css = read("static/css/screener.css")
    ledger = read("static/js/ai_pick_ledger_v52.js")
    assert "window.__openScreenerDiscoveryView?.()" in nav
    assert "window.__openScreenerDiscoveryView = () => openView('screener')" in ledger
    assert "window.__openScreenerAtTop?.()" in nav
    assert "window.__resetScreenerScroll = resetScreenerScroll" in js
    assert "window.__openScreenerAtTop = function" in js
    assert "function settleScreenerAtTop()" in js
    assert "[40, 100, 220].forEach((delay) => setTimeout(pin, delay))" in js
    assert "scroller.scrollTop = 0" in js
    assert "data-screener-top" in js
    assert "기술점수 높은순" in js
    assert 'class="screen-rank"' in js
    assert ".screener-to-top{" in css


def test_p1_home_pick_and_news_hierarchy():
    pick = read("static/js/ai_daily_widget.js")
    news = read("static/js/personalized_news_v40.js")
    watch = read("static/js/home_watchlist_compact_v46.js")
    assert "오늘 선정 PICK" in pick
    assert "최근 선정 PICK" in pick
    assert "추천 건별 평균 수익률" in pick
    assert "watchlist.insertAdjacentElement('afterend',s)" in pick
    assert "직접 관련 뉴스" in news
    assert "업종·간접 관련" in news
    assert "MY STOCKS · 가격 / 1달 수익률" in watch



def test_screener_price_is_labeled_as_trade_date_close_not_realtime():
    js = read("static/js/screener.js")
    css = read("static/css/screener.css")
    assert "<th>기준 종가</th>" in js
    assert 'data-label="기준 종가"' in js
    assert "종가 기준" in js
    assert "shortTradeDate(row.date || payload.tradeDate)" in js
    assert "전일 대비" in js
    assert "가격은 실시간 현재가가 아니라 스크리너 기준 거래일의 종가입니다." in js
    assert "<th>현재가</th>" not in js
    assert 'data-label="현재가"' not in js
    assert ".screen-price-basis" in css
    assert ".screen-close-price" in css


def test_screener_freshness_targets_new_render_backend():
    workflow = read(".github/workflows/screener-production-freshness.yml")
    assert "https://chart-view-pkv8.onrender.com" in workflow
    assert "https://chart-view-bsg6.onrender.com" not in workflow


def test_home_pick_bootstrap_prefers_latest_version_and_disables_stale_cache():
    main = read("main.py")
    assert 'versions = [str(rankings.get("updated") or ""), str(recommendations.get("updated") or "")]' in main
    assert '"version": max(versions)' in main
    assert '"Cache-Control": "no-cache, max-age=0, must-revalidate"' in main


def test_intekplus_is_kept_only_on_2026_09_14_after_user_correction():
    import json
    rankings = json.loads(read("static/data/ai_daily_rankings.json"))
    ledger = json.loads(read("static/data/ai_recommendations.json"))

    day_14 = next(row for row in rankings.get("days", []) if row.get("tradeDate") == "2026-09-14")
    assert any(row.get("name") == "인텍플러스" for row in day_14.get("top3", []))

    day_17 = next(row for row in rankings.get("days", []) if row.get("tradeDate") == "2026-09-17")
    day_21 = next(row for row in rankings.get("days", []) if row.get("tradeDate") == "2026-09-21")
    assert [row.get("name") for row in day_17.get("top3", [])] == ["펌텍코리아", "이오테크닉스"]
    assert [row.get("name") for row in day_21.get("top3", [])] == ["삼성전자", "효성중공업"]

    intek_rows = [
        row for row in ledger.get("recommendations", [])
        if row.get("symbol") == "064290.KQ"
    ]
    assert [row.get("recommendedDate") for row in intek_rows] == ["2026-09-14"]
