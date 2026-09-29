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
            "title": "테스트장비사 A, SK하이닉스 납품 확대",
            "summarySeed": "SK하이닉스 납품 물량을 확대했다.",
            "source": "example.com",
            "publishedAt": "2026-09-29T01:00:00+00:00",
            "url": "https://example.com/new",
        },
        {
            "relationType": "direct",
            "title": "테스트장비사 A, SK하이닉스 고객사 확보",
            "summarySeed": "SK하이닉스를 고객사로 확보했다.",
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

