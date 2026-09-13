from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v393_visual_css_is_preserved_but_unstable_js_is_retired():
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    assert "/static/css/clarity_v39_3.css?v=20260913v393" in boot
    assert "/static/js/clarity_v39_3.js" not in boot
    assert "/static/js/personalization_v36.js" not in boot
    assert "home.dataset.uiVersion = 'v40-stage12'" in boot


def test_v40_detail_uses_explicit_state_instead_of_mutation_observer():
    detail = (ROOT / "static/js/single_detail_v40.js").read_text(encoding="utf-8")
    state = (ROOT / "static/js/app_state_v40.js").read_text(encoding="utf-8")
    assert "MutationObserver" not in detail
    assert "beginDetail" in state and "isCurrentDetail" in state
    assert "AbortController" in detail
    assert "비교 중" in detail
    assert "비교에 추가" in detail
    assert "비교목록 관리" in detail
    assert "history.pushState" in detail
    assert "history.replaceState" in detail


def test_v40_numeric_normalization_does_not_turn_missing_into_zero():
    state = (ROOT / "static/js/app_state_v40.js").read_text(encoding="utf-8")
    detail = (ROOT / "static/js/single_detail_v40.js").read_text(encoding="utf-8")
    assert "value === null || value === undefined || value === ''" in state
    assert "!Number.isFinite(parsed)" in state
    assert "Math.abs(num(value?.roe)" not in detail
    assert "API 제공 ROE 단위 그대로 표시" in detail
    assert "분모 0" in state


def test_v40_preserves_stored_empty_compare_list():
    state = (ROOT / "static/js/app_state_v40.js").read_text(encoding="utf-8")
    assert "if (raw === null)" in state
    assert "return { value: JSON.parse(raw), source: 'stored' }" in state
    assert "DEFAULT_COMPARE" in state


def test_v40_home_price_and_mobile_readability_contract():
    css = (ROOT / "static/css/release_ui_v40.css").read_text(encoding="utf-8")
    assert "text-overflow: clip" in css
    assert "white-space: nowrap" in css
    assert "-webkit-line-clamp: 2" in css
    assert "@media (max-width: 720px)" in css
    assert "@media (max-width: 390px)" in css
    assert "min-height: 44px" in css
    assert "--v40-up: #dc2626" in css
    assert "--v40-down: #2563eb" in css


def test_v40_trade_basis_and_forward_period_copy_are_explicit():
    detail = (ROOT / "static/js/single_detail_v40.js").read_text(encoding="utf-8")
    assert "거래 기준" in detail
    assert "브라우저 조회" in detail
    assert "예상 기간 미확인" in detail
    assert "1달 수익률 차트" in detail
    assert "기간 시작 대비 수익률 흐름" in detail
