"""Curriculum and pinned lesson contracts, without network or market providers."""

from copy import deepcopy
from datetime import date, timedelta
import importlib
from urllib.parse import urlparse

import pytest


def content():
    return importlib.import_module("learning_content")


EXPECTED_COMPANIES = [
    ("278470.KS", "에이피알", "화장품"),
    ("192820.KS", "코스맥스", "화장품"),
    ("161890.KS", "한국콜마", "화장품"),
    ("003230.KS", "삼양식품", "K-푸드"),
    ("004370.KS", "농심", "K-푸드"),
    ("097950.KS", "CJ제일제당", "K-푸드"),
    ("042660.KS", "한화오션", "조선·LNG"),
    ("010140.KS", "삼성중공업", "조선·LNG"),
    ("009540.KS", "HD한국조선해양", "조선·LNG"),
    ("012450.KS", "한화에어로스페이스", "방산"),
    ("079550.KS", "LIG넥스원", "방산"),
    ("064350.KS", "현대로템", "방산"),
    ("034020.KS", "두산에너빌리티", "원전"),
    ("000720.KS", "현대건설", "원전"),
    ("051600.KS", "한전KPS", "원전"),
    ("267260.KS", "HD현대일렉트릭", "전력기기"),
    ("010120.KS", "LS ELECTRIC", "전력기기"),
    ("062040.KS", "산일전기", "전력기기"),
]


def test_catalog_preserves_all_requested_identities_and_industry_order():
    result = content().catalog()
    assert result["schemaVersion"] == 1
    assert [(c["symbol"], c["name"], c["industry"]) for c in result["companies"]] == EXPECTED_COMPANIES
    assert result["curriculum"]["startDate"] == "2026-11-02"
    assert [len(w["companies"]) for w in result["curriculum"]["weeks"]] == [3] * 6


@pytest.mark.parametrize("day,kind,symbols", [
    ("2026-11-02", "company", ["278470.KS"]),
    ("2026-11-03", "company", ["192820.KS"]),
    ("2026-11-04", "company", ["161890.KS"]),
    ("2026-11-05", "value_chain", ["278470.KS", "192820.KS", "161890.KS"]),
    ("2026-11-06", "comparison", ["278470.KS", "192820.KS", "161890.KS"]),
    ("2026-11-07", "scenario", ["278470.KS", "192820.KS", "161890.KS"]),
    ("2026-11-08", "review", ["278470.KS", "192820.KS", "161890.KS"]),
    ("2026-11-09", "company", ["003230.KS"]),
    ("2026-12-13", "review", ["267260.KS", "010120.KS", "062040.KS"]),
])
def test_weekday_schedule_and_last_day(day, kind, symbols):
    lesson = content().build_lesson(content().default_curriculum(), day)
    assert lesson["date"] == day
    assert lesson["kind"] == kind
    assert [c["symbol"] for c in lesson["companies"]] == symbols


def test_every_scheduled_day_has_an_independent_usable_25_minute_lesson():
    curriculum = content().default_curriculum()
    lessons = [content().build_lesson(curriculum, (date(2026, 11, 2) + timedelta(days=i)).isoformat()) for i in range(42)]
    assert len({lesson["id"] for lesson in lessons}) == 42
    assert [lesson["kind"] for lesson in lessons].count("company") == 18
    for lesson in lessons:
        assert lesson["duration"] == 25
        assert sum(section["minutes"] for section in lesson["sections"]) == 25
        assert all(section["body"] and section["prompts"] for section in lesson["sections"])
        assert {q["dimension"] for q in lesson["questions"]} == {"business", "inference"}
        assert len(lesson["questions"]) >= 4
        assert len({q["id"] for q in lesson["questions"]}) == len(lesson["questions"])
        for q in lesson["questions"]:
            assert len(q["options"]) >= 3
            assert 0 <= q["correctIndex"] < len(q["options"])
            assert q["explanation"] and q["concept"]
        assert "근거" in lesson["judgmentPrompt"]
        for source in lesson["sources"]:
            parsed = urlparse(source["url"])
            assert parsed.scheme == "https" and parsed.netloc and not parsed.username
        assert any(urlparse(s["url"]).hostname == "dart.fss.or.kr" for s in lesson["sources"])


@pytest.mark.parametrize("bad_date", ["2026-11-01", "2026-12-14", "2026-02-30", "2026-1-02", "2026-11-02T00:00:00Z", "", None])
def test_missing_schedule_or_non_calendar_date_never_becomes_a_fake_lesson(bad_date):
    with pytest.raises(ValueError):
        content().build_lesson(content().default_curriculum(), bad_date)


def test_public_lesson_redacts_answers_without_mutating_the_pinned_definition():
    private = content().build_lesson(content().default_curriculum(), "2026-11-02")
    original = deepcopy(private)
    public = content().public_lesson(private)
    assert private == original
    assert public["quizVersion"] == private["quizVersion"]
    for question in public["questions"]:
        assert set(question) == {"id", "dimension", "prompt", "options"}
    public["questions"][0]["options"][0] = "client edit"
    assert private == original


def test_quiz_version_is_deterministic_and_changes_when_the_answer_definition_changes():
    lesson = content().build_lesson(content().default_curriculum(), "2026-11-02")
    assert lesson["quizVersion"] == content().build_lesson(content().default_curriculum(), "2026-11-02")["quizVersion"]
    changed = deepcopy(lesson)
    question = changed["questions"][0]
    question["correctIndex"] = (question["correctIndex"] + 1) % len(question["options"])
    assert content().public_lesson(changed)["quizVersion"] != lesson["quizVersion"]


def test_catalog_and_curriculum_are_copied_for_each_account():
    catalog = content().catalog()
    catalog["companies"][0]["name"] = "changed"
    catalog["curriculum"]["weeks"][0]["companies"].clear()
    assert content().catalog()["companies"][0]["name"] == "에이피알"
    assert len(content().default_curriculum()["weeks"][0]["companies"]) == 3


def test_public_curriculum_validation_returns_a_normalized_independent_copy():
    curriculum = content().default_curriculum()
    curriculum["title"] = "  편집한 공부  "
    validated = content().validate_curriculum(curriculum)
    assert validated["title"] == "편집한 공부"
    assert curriculum["title"] == "  편집한 공부  "
    validated["weeks"][0]["companies"].clear()
    assert len(curriculum["weeks"][0]["companies"]) == 3


@pytest.mark.parametrize("mutation", [
    lambda c: c["weeks"][0]["companies"].__setitem__(1, deepcopy(c["weeks"][0]["companies"][0])),
    lambda c: c["weeks"][1].update(id=c["weeks"][0]["id"]),
    lambda c: c.update(id="x" * 121),
    lambda c: c.update(title="x" * 201),
    lambda c: c["weeks"][0].update(id="x" * 121),
    lambda c: c["weeks"][0].update(industry="x" * 81),
    lambda c: c["weeks"][0]["companies"][0].update(name="x" * 121),
    lambda c: c["weeks"][0]["companies"][0].update(industry="x" * 81),
])
def test_public_curriculum_validation_rejects_duplicates_and_oversized_fields(mutation):
    curriculum = content().default_curriculum()
    mutation(curriculum)
    with pytest.raises(ValueError):
        content().validate_curriculum(curriculum)


def test_custom_curriculum_moves_dates_and_extends_without_changing_pinned_lessons():
    curriculum = content().default_curriculum()
    pinned = content().build_lesson(curriculum, "2026-11-02")
    original = deepcopy(pinned)
    curriculum["startDate"] = "2027-01-04"
    curriculum["weeks"] = [deepcopy(curriculum["weeks"][5])]
    curriculum["weeks"][0]["id"] = "custom-power"
    lesson = content().build_lesson(curriculum, "2027-01-04")
    assert lesson["companies"][0]["symbol"] == "267260.KS"
    assert lesson["industry"] == "전력기기"
    assert pinned == original
    with pytest.raises(ValueError):
        content().build_lesson(curriculum, "2027-01-11")


@pytest.mark.parametrize("mutation", [
    lambda c: c.update(startDate="2026-11-03"),
    lambda c: c.update(startDate="2026-02-30"),
    lambda c: c.update(weeks=[]),
    lambda c: c.update(weeks=c["weeks"] * 18),
    lambda c: c["weeks"][0].update(companies=[]),
    lambda c: c["weeks"][0].update(companies=c["weeks"][0]["companies"][:2]),
    lambda c: c["weeks"][0].update(industry=""),
    lambda c: c["weeks"][0]["companies"][0].update(symbol="../../private"),
])
def test_invalid_curriculum_is_rejected_before_building(mutation):
    curriculum = content().default_curriculum()
    mutation(curriculum)
    with pytest.raises(ValueError):
        content().build_lesson(curriculum, "2026-11-02")


def test_explicit_known_company_allows_a_new_dated_study_after_the_schedule():
    lesson = content().build_lesson(content().default_curriculum(), "2027-01-01", symbol="062040.KS")
    assert lesson["kind"] == "company"
    assert lesson["companies"] == [{"symbol": "062040.KS", "name": "산일전기", "industry": "전력기기"}]
    assert lesson["date"] == "2027-01-01"


def test_custom_company_lesson_labels_unknown_facts_and_uses_general_evidence_questions():
    custom = {"symbol": "CUSTOM", "name": "확인이 필요한 기업", "industry": "기타"}
    lesson = content().build_lesson(content().default_curriculum(), "2027-01-01", company=custom)
    assert lesson["companies"] == [custom]
    assert lesson["kind"] == "company"
    body = " ".join(s["body"] for s in lesson["sections"])
    assert "미확인" in body
    assert "직접" in body and "공시" in body
    assert any("기간" in q["explanation"] for q in lesson["questions"])
    with pytest.raises(ValueError):
        content().build_lesson(content().default_curriculum(), "2027-01-01", symbol="CUSTOM")


def test_replacing_week_companies_does_not_apply_the_old_industry_to_company_study():
    curriculum = content().default_curriculum()
    curriculum["weeks"][0]["companies"] = deepcopy(curriculum["weeks"][5]["companies"])
    company_lesson = content().build_lesson(curriculum, "2026-11-02")
    assert company_lesson["industry"] == "전력기기"
    scenario_question = next(q for q in company_lesson["questions"] if q["id"] == "inference-transmission")
    assert "전력망" in scenario_question["prompt"]
    group_lesson = content().build_lesson(curriculum, "2026-11-05")
    assert all("화장품 수요" not in q["prompt"] for q in group_lesson["questions"])


def test_custom_identities_under_known_industry_still_get_unknown_fact_guidance():
    curriculum = content().default_curriculum()
    companies = [{"symbol": f"CUSTOM{i}", "name": f"미확인기업{i}", "industry": "화장품"} for i in range(3)]
    curriculum["weeks"][0]["companies"] = companies
    lesson = content().build_lesson(curriculum, "2026-11-05")
    public = content().public_lesson(lesson)
    payload = str(public)
    assert "에이피알" not in payload and "코스맥스" not in payload and "한국콜마" not in payload
    assert "미확인" in payload
    question = next(q for q in lesson["questions"] if q["id"] == "inference-transmission")
    assert "미확인" in question["prompt"]
    standalone = content().build_lesson(curriculum, "2027-01-01", company=companies[0])
    question = next(q for q in standalone["questions"] if q["id"] == "inference-transmission")
    assert "미확인" in question["prompt"]


@pytest.mark.parametrize("symbol,business_term", [
    ("278470.KS", "뷰티"), ("192820.KS", "ODM"), ("161890.KS", "ODM"),
    ("003230.KS", "라면"), ("004370.KS", "라면"), ("097950.KS", "바이오"),
    ("042660.KS", "선박"), ("010140.KS", "해양"), ("009540.KS", "자회사"),
    ("012450.KS", "엔진"), ("079550.KS", "유도무기"), ("064350.KS", "철도"),
    ("034020.KS", "주기기"), ("000720.KS", "건설"), ("051600.KS", "정비"),
    ("267260.KS", "변압기"), ("010120.KS", "자동화"), ("062040.KS", "변압기"),
])
def test_each_company_has_specific_business_primer_and_quiz(symbol, business_term):
    lesson = content().build_lesson(content().default_curriculum(), "2026-11-02", symbol=symbol)
    assert business_term in " ".join(s["body"] for s in lesson["sections"])
    business_questions = [q for q in lesson["questions"] if q["dimension"] == "business"]
    assert any(business_term in q["options"][q["correctIndex"]] for q in business_questions)
    assert any("기준일" in p or "기간" in p for s in lesson["sections"] for p in s["prompts"])
