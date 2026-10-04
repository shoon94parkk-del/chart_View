import asyncio
import time
from unittest.mock import patch

import relationship_evidence_service as service
import news_service_v37 as news
from relationship_evidence_service import extract_direct_relations


COMPANIES = [
    {"name": "삼성전자", "symbol": "005930.KS"},
    {"name": "SK하이닉스", "symbol": "000660.KS"},
    {"name": "HLB제약", "symbol": "047920.KQ"},
]

def test_explicit_retry_bypasses_failed_relationship_and_news_caches(monkeypatch):
    service._CACHE.clear()
    news.NEWS_CACHE.clear()
    calls = []
    def provider(symbol, name):
        calls.append(symbol)
        return {"items": [], "error": "temporary_failure"} if len(calls) == 1 else {"items": []}
    monkeypatch.setattr(news, "_fetch_naver_news", provider)
    first = service.fetch_relationship_evidence("005930.KS", "삼성전자")
    assert first["reason"] == "news_provider_unavailable"
    # Ordinary reads reuse existing cache; an explicit retry must reach provider.
    service.fetch_relationship_evidence("005930.KS", "삼성전자")
    assert len(calls) == 1
    retry = service.fetch_relationship_evidence("005930.KS", "삼성전자", force=True)
    assert len(calls) == 2
    assert retry["reason"] == "no_evidence_backed_direct_relation"
    service._CACHE.clear()
    news.NEWS_CACHE.clear()

def test_shared_suppliers_in_third_party_article_are_not_each_others_contract_party():
    item = {
        "relationType": "direct",
        "title": "브로드컴, 앤트로픽에 지원",
        "summarySeed": "삼성전자, SK하이닉스, 마이크론 등 메모리 반도체 3사도 고성능 메모리 공급을 위한 핵심 전략적 파트너로 투자설명서에 이름을 올렸다 앤트로픽은 장기 계약을 체결한 배경을 설명했다",
        "url": "https://example.com/third-party",
    }
    assert extract_direct_relations("삼성전자", "005930.KS", [item], COMPANIES) == []

def test_co_suppliers_with_a_common_customer_are_not_a_direct_pair():
    item = {
        "relationType": "direct",
        "title": "삼성전자와 SK하이닉스, 고객사와 공급계약 체결",
        "summarySeed": "삼성전자와 SK하이닉스는 앤트로픽과 공급계약을 체결했다",
        "url": "https://example.com/co-suppliers",
    }
    assert extract_direct_relations("삼성전자", "005930.KS", [item], COMPANIES) == []

def test_explicit_reverse_party_and_direction_remain_valid():
    item = {
        "relationType": "direct",
        "title": "SK하이닉스는 삼성전자와 장비 공급계약을 체결했다",
        "url": "https://example.com/pair",
    }
    rows = extract_direct_relations("삼성전자", "005930.KS", [item], COMPANIES)
    assert [row["counterpartyName"] for row in rows] == ["SK하이닉스"]

def test_peer_comparison_particle_does_not_make_a_contract_role():
    item = {
        "relationType": "direct",
        "title": "메모리 공급사 관련 기사",
        "summarySeed": "삼성전자는 SK하이닉스와 같은 메모리 공급사다 고객사는 다른 업체와 계약을 체결했다",
        "url": "https://example.com/peer-description",
    }
    assert extract_direct_relations("삼성전자", "005930.KS", [item], COMPANIES) == []


def test_requires_named_counterparty_and_strong_commercial_keyword():
    items = [{
        "relationType": "direct",
        "title": "테스트장비사 A, 삼성전자와 공급계약 체결",
        "summarySeed": "테스트장비사 A가 삼성전자와 신규 공급계약을 체결했다.",
        "source": "example.com",
        "publishedAt": "2026-09-29T00:00:00+00:00",
        "url": "https://example.com/a",
    }]
    rows = extract_direct_relations("테스트장비사 A", "123456.KQ", items, COMPANIES)
    assert len(rows) == 1
    assert rows[0]["counterpartyName"] == "삼성전자"
    assert rows[0]["relationLabel"] == "공급·납품"


def test_does_not_upgrade_industry_mentions_without_relationship_evidence():
    items = [{
        "relationType": "direct",
        "title": "테스트장비사 A, 삼성전자·SK하이닉스 강세에 동반 상승",
        "summarySeed": "반도체 업종 전반이 올랐다.",
        "source": "example.com",
        "publishedAt": "2026-09-29T00:00:00+00:00",
        "url": "https://example.com/b",
    }]
    assert extract_direct_relations("테스트장비사 A", "123456.KQ", items, COMPANIES) == []


def test_ignores_unverified_news_even_with_contract_words():
    items = [{
        "relationType": "unverified",
        "title": "삼성전자 공급계약 관련 시장 소문",
        "summarySeed": "공급계약 가능성이 거론됐다.",
        "source": "example.com",
        "publishedAt": "2026-09-29T00:00:00+00:00",
        "url": "https://example.com/c",
    }]
    assert extract_direct_relations("테스트장비사 A", "123456.KQ", items, COMPANIES) == []


def test_keeps_one_fresh_evidence_per_counterparty():
    items = [
        {
            "relationType": "direct",
            "title": "테스트장비사 A, SK하이닉스에 납품계약 체결",
            "summarySeed": "테스트장비사 A가 SK하이닉스에 납품계약을 체결했다.",
            "source": "example.com",
            "publishedAt": "2026-09-29T01:00:00+00:00",
            "url": "https://example.com/new",
        },
        {
            "relationType": "direct",
            "title": "테스트장비사 A, SK하이닉스를 고객사로 확보",
            "summarySeed": "테스트장비사 A가 SK하이닉스를 고객사로 확보했다.",
            "source": "example.com",
            "publishedAt": "2026-09-28T01:00:00+00:00",
            "url": "https://example.com/old",
        },
    ]
    rows = extract_direct_relations("테스트장비사 A", "123456.KQ", items, COMPANIES)
    assert len(rows) == 1
    assert rows[0]["url"].endswith("/new")

def test_rejects_speculative_relationship_language_even_when_company_is_named():
    items = [{
        "relationType": "direct",
        "title": "테스트장비사 A, 삼성전자 공급계약 가능성 거론",
        "summarySeed": "삼성전자 공급계약 가능성이 시장에서 거론됐다.",
        "source": "example.com",
        "publishedAt": "2026-09-29T00:00:00+00:00",
        "url": "https://example.com/speculative",
    }]
    assert extract_direct_relations("테스트장비사 A", "123456.KQ", items, COMPANIES) == []


def test_rejects_ended_or_cancelled_relationships():
    items = [{
        "relationType": "direct",
        "title": "테스트장비사 A, SK하이닉스 공급계약 해지",
        "summarySeed": "SK하이닉스와의 공급계약을 해지했다.",
        "source": "example.com",
        "publishedAt": "2026-09-29T00:00:00+00:00",
        "url": "https://example.com/ended",
    }]
    assert extract_direct_relations("테스트장비사 A", "123456.KQ", items, COMPANIES) == []


def test_roundup_with_unrelated_contracts_is_not_a_direct_relationship():
    items = [{
        "relationType": "direct",
        "title": "오늘의 특징주: 삼성전자, 테라뷰 공급계약 소식에 강세",
        "summarySeed": "삼성전자 주가가 올랐다. 테라뷰는 미국 기업과 공급계약을 체결했다.",
        "url": "https://example.com/roundup",
    }, {
        "relationType": "direct",
        "title": "기업 공시 [9월 29일]",
        "summarySeed": "에스원이 삼성전자와 미화 계약 체결 ▲현대오토에버는 다른 기업과 공급계약 체결",
        "url": "https://example.com/disclosure",
    }]
    companies = COMPANIES + [
        {"name": "테라뷰", "symbol": "123450.KQ"},
        {"name": "현대오토에버", "symbol": "307950.KS"},
    ]
    assert extract_direct_relations("삼성전자", "005930.KS", items, companies) == []


def test_sector_order_backlog_is_not_a_contract_between_peer_shipbuilders():
    item = {
        "relationType": "direct",
        "title": "한화오션과 HD한국조선해양, 조선 3사 수주잔고 증가",
        "summarySeed": "한화오션과 HD한국조선해양의 수주잔고가 함께 늘었다.",
        "url": "https://example.com/ships",
    }
    companies = COMPANIES + [{"name": "HD한국조선해양", "symbol": "009540.KS"}]
    assert extract_direct_relations("한화오션", "042660.KS", [item], companies) == []


def test_company_name_embedded_in_longer_issuer_is_not_counterparty():
    item = {
        "relationType": "direct",
        "title": "SK하이닉스, HBM4 고객사 확대",
        "summarySeed": "SK하이닉스가 고객사로 선정됐다.",
        "url": "https://example.com/embedded",
    }
    companies = COMPANIES + [{"name": "이닉스", "symbol": "452400.KQ"}]
    assert extract_direct_relations("SK하이닉스", "000660.KS", [item], companies) == []


def test_dedicated_story_can_show_explicit_customer_contract_without_prefix_match():
    item = {
        "relationType": "direct",
        "title": "동성화인텍, LNG 보냉재 공급계약 체결",
        "summarySeed": "지난달 삼성중공업과 HD현대중공업에게서 초저온 보냉자재 공급계약을 따냈다.",
        "url": "https://example.com/insulation",
    }
    companies = COMPANIES + [
        {"name": "삼성중공업", "symbol": "010140.KS"},
        {"name": "HD현대중공업", "symbol": "329180.KS"},
        {"name": "HD현대", "symbol": "267250.KS"},
    ]
    rows = extract_direct_relations("동성화인텍", "033500.KQ", [item], companies)
    assert {row["counterpartyName"] for row in rows} == {"삼성중공업", "HD현대중공업"}


def test_morning_economic_briefing_does_not_link_unrelated_disclosures():
    item = {
        "relationType": "direct",
        "title": "[N2 모닝 경제 브리핑-9월 29일] 美 증시와 기업 소식",
        "summarySeed": "수주 - 한화오션 : 자기주식 취득 결정 - 티케이지휴켐스 : 질산 공급 계약 체결 - 달바글로벌 : NH투자증권과 신탁계약 체결",
        "url": "https://example.com/morning",
    }
    companies = COMPANIES + [
        {"name": "티케이지휴켐스", "symbol": "069260.KS"},
        {"name": "달바글로벌", "symbol": "483650.KS"},
        {"name": "NH투자증권", "symbol": "005940.KS"},
    ]
    assert extract_direct_relations("한화오션", "042660.KS", [item], companies) == []


def test_unlisted_longer_company_name_does_not_create_listed_prefix_relation():
    item = {
        "relationType": "direct",
        "title": "동성화인텍, LNG 보냉재 계약 체결",
        "summarySeed": "동성화인텍은 HD현대중공업 및 HD현대삼호와 공급계약을 체결했다.",
        "url": "https://example.com/samho",
    }
    companies = COMPANIES + [
        {"name": "HD현대", "symbol": "267250.KS"},
        {"name": "HD현대중공업", "symbol": "329180.KS"},
    ]
    rows = extract_direct_relations("동성화인텍", "033500.KQ", [item], companies)
    assert [row["counterpartyName"] for row in rows] == ["HD현대중공업"]


def test_no_relation_returns_from_general_news_without_serial_targeted_searches():
    with patch.object(service, "_cached_fetch", return_value={"items": [], "error": None, "provider": "test"}):
        result = service.fetch_relationship_evidence("005930.KS", "삼성전자")
    assert result["relations"] == []
    assert result["searchMode"] == "general"
    assert result["targetedSearchCount"] == 0


def test_slow_news_provider_returns_bounded_unavailable_state():
    def slow_fetch(*_args):
        time.sleep(.03)
        return {"ticker": "005930.KS", "available": False, "relations": []}

    with patch.object(service, "fetch_relationship_evidence", side_effect=slow_fetch), patch.object(service, "RESPONSE_TIMEOUT", .005):
        result = asyncio.run(service.relationship_evidence(ticker="005930.KS", name="삼성전자"))
    assert result["available"] is False
    assert result["reason"] == "provider_timeout"

