from relationship_evidence_service import extract_direct_relations


COMPANIES = [
    {"name": "삼성전자", "symbol": "005930.KS"},
    {"name": "SK하이닉스", "symbol": "000660.KS"},
    {"name": "HLB제약", "symbol": "047920.KQ"},
]


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

