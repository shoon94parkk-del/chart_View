import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/js/ai_pick_ledger_v52.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/ai_pick_ledger_v52.css").read_text(encoding="utf-8")
MONITOR = json.loads((ROOT / "static/data/pick_monitor.json").read_text(encoding="utf-8"))
REVIEWS = json.loads((ROOT / "static/data/pick_monitor_reviews.json").read_text(encoding="utf-8"))


def test_monitor_is_visible_inside_ai_pick_discovery_shell():
    assert 'data-discovery-view="pick-monitor"' in JS
    assert 'data-discovery-panel="pick-monitor"' in JS
    assert "기존 PICK 점검" in JS
    assert "pick_monitor.json?v=monitor1" in JS


def test_monitor_ui_exposes_safe_status_language():
    assert "매도검토" in JS
    assert "사용자 확인 필요" in JS
    assert "가격·차트만으로 매도검토하지 않음" in JS
    assert "자동 매도 확정이 아니며 사용자 확인이 필요" in JS


def test_monitor_cards_show_thesis_review_evidence_and_dates():
    for token in ("추천 당시 논리", "최근 점검", "검증 근거", "마지막 검토", "시세기준"):
        assert token in JS
    assert "sourceUrl" in JS
    assert "lastReviewedTradeDate" in JS


def test_mobile_subnav_has_three_columns_and_monitor_cards():
    assert "repeat(3,minmax(0,1fr))" in CSS
    assert ".ai-monitor-card" in CSS
    assert ".ai-monitor-status-sell-review" in CSS


def test_seed_reviews_are_post_pick_and_verified():
    by_id = {row["pickId"]: row for row in MONITOR["picks"]}
    assert REVIEWS["reviews"]
    for review in REVIEWS["reviews"]:
        pick = by_id[review["pickId"]]
        assert review["completed"] is True
        assert review["evidence"]
        for evidence in review["evidence"]:
            assert evidence["verified"] is True
            assert evidence["publishedAt"] >= pick["pickDate"]
            assert evidence["sourceUrl"].startswith("http")


def test_initial_p1_state_does_not_invent_sell_signals():
    statuses = [row["status"] for row in MONITOR["picks"]]
    assert statuses.count("KEEP") == 5
    assert statuses.count("PENDING_REVIEW") == 14
    assert statuses.count("WATCH") == 0
    assert statuses.count("SELL_REVIEW") == 0


VISIBLE_JS = (ROOT / "static/js/pick_monitor_visible_tab_v1.js").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates/index.html").read_text(encoding="utf-8")


def test_pick_monitor_has_visible_top_level_discovery_tab():
    assert "PICK 점검" in VISIBLE_JS
    assert 'data-app-context="discover"' in VISIBLE_JS
    assert "repeat(3,minmax(0,1fr))" in VISIBLE_JS
    assert "pick_monitor.json" in VISIBLE_JS
    assert "ai_recommendations.json" in VISIBLE_JS


def test_visible_pick_monitor_is_part_of_single_boot_bundle():
    build = (ROOT / "scripts/build_boot_bundle.py").read_text(encoding="utf-8")
    boot = (ROOT / "static/js/chartview_boot_bundle.js").read_text(encoding="utf-8")
    assert '"static/js/pick_monitor_visible_tab_v1.js"' in build
    assert "/* --- static/js/pick_monitor_visible_tab_v1.js --- */" in boot
    assert "PICK 점검" in boot
    assert "pick_monitor_visible_tab_v1.js?v=" not in TEMPLATE


def test_visible_pick_monitor_keeps_sell_review_safe():
    assert "매도검토는 자동 매도 확정이 아닙니다." in VISIBLE_JS
    assert "가격·차트만으로 매도검토하지 않음" in VISIBLE_JS
    assert "사용자 확인 필요" in VISIBLE_JS
