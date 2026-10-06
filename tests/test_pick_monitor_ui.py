import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITOR = json.loads((ROOT / "static/data/pick_monitor.json").read_text(encoding="utf-8"))
REVIEWS = json.loads((ROOT / "static/data/pick_monitor_reviews.json").read_text(encoding="utf-8"))
VISIBLE_JS = (ROOT / "static/js/pick_monitor_visible_tab_v1.js").read_text(encoding="utf-8")
DAILY_JS = (ROOT / "static/js/ai_daily_widget.js").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates/index.html").read_text(encoding="utf-8")


def test_pick_management_is_top_level_discovery_tab():
    assert "PICK 관리" in VISIBLE_JS
    assert 'data-app-context="discover"' in VISIBLE_JS
    assert "repeat(3,minmax(0,1fr))" in VISIBLE_JS
    assert "PICK 기록 · 점검" not in VISIBLE_JS
    assert "시장 스크리너" not in VISIBLE_JS


def test_pick_management_combines_performance_and_monitoring():
    for token in ("누적 추천일", "누적 추천 건수", "수익 구간 비율", "건별 평균 수익률"):
        assert token in VISIBLE_JS
    for token in ("유지", "경계", "매도검토", "검토 대기"):
        assert token in VISIBLE_JS
    for token in ("추천 당시 이유", "투자논리 기준선", "최근 점검", "검증 근거", "마지막 점검"):
        assert token in VISIBLE_JS
    assert "ai_recommendations.json" in VISIBLE_JS
    assert "pick_monitor.json" in VISIBLE_JS


def test_pick_management_filters_cover_history_and_monitor_status():
    for token in ("종목명 · 코드 검색", "기간 전체", "성과 전체", "상태 전체", "점검 우선순"):
        assert token in VISIBLE_JS


def test_home_full_history_opens_top_level_pick_management():
    assert "__openPickManagement" in DAILY_JS
    click_region = DAILY_JS[DAILY_JS.index("document.addEventListener('click'"):DAILY_JS.index("function scheduleMount")]
    assert "installAiLedgerAssets()" not in click_region


def test_pick_management_keeps_sell_review_safe():
    assert "매도검토는 자동 매도 확정이 아니며 가격·차트만으로 판정하지 않습니다." in VISIBLE_JS
    assert "사용자 확인 필요" in VISIBLE_JS


def test_seed_reviews_are_post_pick_and_verified():
    by_id = {row["pickId"]: row for row in MONITOR["picks"]}
    assert REVIEWS["reviews"]
    for review in REVIEWS["reviews"]:
        pick = by_id[review["pickId"]]
        if review["completed"]:
            assert review["evidence"]
            for evidence in review["evidence"]:
                assert evidence["verified"] is True
                assert evidence["publishedAt"] >= pick["pickDate"]
                assert evidence["sourceUrl"].startswith("http")
        else:
            assert review["evidence"] == []
            if pick["status"] == "EXIT":
                assert pick["decision"]["finalizedByUser"] is True
            else:
                assert pick["status"] == "PENDING_REVIEW"


def test_p1_state_does_not_invent_sell_signals():
    statuses = [row["status"] for row in MONITOR["picks"]]
    assert statuses
    assert set(statuses) <= {"KEEP", "PENDING_REVIEW", "EXIT"}
    assert statuses.count("KEEP") > 0
    assert statuses.count("PENDING_REVIEW") > 0
    assert statuses.count("WATCH") == 0
    assert statuses.count("SELL_REVIEW") == 0
    for row in MONITOR["picks"]:
        if row["status"] == "EXIT":
            assert row["decision"]["finalizedByUser"] is True
            assert row["decision"]["exitDate"]
            assert row["decision"]["exitPrice"] is not None


def test_pick_management_is_part_of_single_boot_bundle():
    build = (ROOT / "scripts/build_boot_bundle.py").read_text(encoding="utf-8")
    boot = (ROOT / "static/js/chartview_boot_bundle.js").read_text(encoding="utf-8")
    assert '"static/js/pick_monitor_visible_tab_v1.js"' in build
    assert "/* --- static/js/pick_monitor_visible_tab_v1.js --- */" in boot
    assert "pick_monitor_visible_tab_v1.js?v=" not in TEMPLATE
