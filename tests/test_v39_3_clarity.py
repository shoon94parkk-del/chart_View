from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v393_assets_are_loaded_and_versioned():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "/static/css/clarity_v39_3.css?v=20260913v393" in boot
    assert "/static/js/clarity_v39_3.js?v=20260913v393" in boot
    assert "data-clarity-v393" in boot
    assert "home.dataset.uiVersion = 'v39.3'" in boot


def test_v393_separates_detail_target_from_compare_context():
    js = (ROOT / "static/js/clarity_v39_3.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/clarity_v39_3.css").read_text(encoding="utf-8")
    assert "상세 대상" in js
    assert "비교목록 · 이미 포함" in js
    assert "비교목록이 아니라 현재 상세 대상만 확인합니다" in js
    assert "밸류 보기" in js
    assert "투자판단 보기" in js
    assert "body.v393-detail-open #stock-brief-v8" in css
    assert "window.__openAppTab(restore.mode)" in js
    assert "window.scrollTo({ top: restore.scrollY" in js


def test_v393_preserves_compare_list_on_detail_open():
    js = (ROOT / "static/js/clarity_v39_3.js").read_text(encoding="utf-8")
    assert "localStorage.getItem(SELECTED_KEY)" in js
    assert "localStorage.setItem(SELECTED_KEY" not in js
    assert "window.addGlobalTicker" not in js


def test_v393_watchlist_prices_are_not_ellipsized_and_period_is_close_to_value():
    css = (ROOT / "static/css/clarity_v39_3.css").read_text(encoding="utf-8")
    js = (ROOT / "static/js/clarity_v39_3.js").read_text(encoding="utf-8")
    assert "text-overflow: clip" in css
    assert "white-space: nowrap" in css
    assert "grid-template-columns: 1fr" in css
    assert "v393-period" in js
    assert "1달 수익률" in js
    assert "@media (max-width: 430px)" in css


def test_v393_distinguishes_trade_basis_from_query_time_and_macro_basis():
    js = (ROOT / "static/js/clarity_v39_3.js").read_text(encoding="utf-8")
    assert "거래 기준" in js
    assert "조회" in js
    assert "매크로 관측 기준" in js
    assert "period=1mo" in js
    assert "actualEnd" in js


def test_v393_uses_korean_direction_colors_with_non_color_cues_preserved():
    css = (ROOT / "static/css/clarity_v39_3.css").read_text(encoding="utf-8")
    previous = (ROOT / "static/css/home_visual_v39_1.css").read_text(encoding="utf-8")
    assert ".watchlist-v30-return.up" in css
    assert "#dc2626" in css
    assert ".watchlist-v30-return.down" in css
    assert "#2563eb" in css
    assert 'em.up::before { content: "▲ "' in previous
    assert 'em.down::before { content: "▼ "' in previous
