from pathlib import Path

import news_summary_service as svc

ROOT = Path(__file__).resolve().parents[1]


def test_extract_article_prefers_article_body_over_navigation():
    page = '''
    <html><head><meta name="description" content="짧은 페이지 설명입니다."></head>
    <body><nav>Subscribe and sign in</nav><article>
      <p>Nvidia said quarterly revenue rose 55 percent as data-center demand accelerated sharply across major cloud customers.</p>
      <p>The company also raised its outlook and said next-generation AI chips are moving into volume production this quarter.</p>
    </article></body></html>
    '''
    body, description = svc._extract_article(page)
    assert "quarterly revenue" in body
    assert "next-generation AI chips" in body
    assert "Subscribe" not in body
    assert "페이지 설명" in description


def test_sentence_picker_uses_article_facts_not_headline_copy():
    text = (
        "The company held an employee event on Monday. "
        "Nvidia reported revenue of $60 billion, up 55 percent from a year earlier, driven by data-center demand. "
        "Management raised full-year guidance and expects Blackwell shipments to increase in the next quarter. "
        "The company thanked employees for their work."
    )
    picked = svc._pick_summary_sentences(text, "Nvidia raises guidance after strong revenue")
    assert "$60 billion" in picked
    assert "guidance" in picked.lower()
    assert "employee event" not in picked


def test_build_summary_uses_body_and_returns_korean(monkeypatch):
    svc.SUMMARY_CACHE.clear()
    page = '''<html><body><article>
      <p>Nvidia reported revenue of $60 billion, up 55 percent from a year earlier as demand for AI accelerators remained strong.</p>
      <p>The company raised guidance for the next quarter and expects Blackwell shipments to expand.</p>
    </article></body></html>'''
    monkeypatch.setattr(svc, "_safe_fetch_html", lambda url: (page, url))

    def fake_translate(text):
        if "Nvidia" in text and len(text) < 120:
            return "엔비디아, 강한 매출 성장에 다음 분기 전망 상향", True
        return "엔비디아는 AI 가속기 수요로 매출이 전년 대비 55% 증가한 600억 달러를 기록했고, 다음 분기 가이던스를 상향하며 블랙웰 출하 확대를 전망했다.", True

    monkeypatch.setattr(svc, "_translate_ko", fake_translate)
    result = svc._build_summary("https://example.com/news/1", "Nvidia raises guidance", "")
    assert result["basis"] == "article_body"
    assert result["basisLabel"] == "본문 기반"
    assert "매출" in result["summary"] and "가이던스" in result["summary"]
    assert result["titleKo"].startswith("엔비디아")


def test_short_provider_snippet_becomes_title_snippet_fallback(monkeypatch):
    svc.SUMMARY_CACHE.clear()
    monkeypatch.setattr(svc, "_safe_fetch_html", lambda url: (_ for _ in ()).throw(RuntimeError("blocked")))

    def fake_translate(text):
        if text == "Micron signs new memory contract":
            return "마이크론, 신규 메모리 공급 계약 체결", True
        return "마이크론이 신규 메모리 공급 계약을 체결했다. AI 메모리 수요 확대와 관련된 내용이다.", True

    monkeypatch.setattr(svc, "_translate_ko", fake_translate)
    result = svc._build_summary(
        "https://example.com/news/short",
        "Micron signs new memory contract",
        "AI memory demand supports the agreement.",
    )
    assert result["basis"] == "title_snippet_fallback"
    assert result["basisLabel"] == "제목·요약문 기반"
    assert "만들지 못했습니다" not in result["summary"]
    assert "마이크론" in result["summary"]


def test_headline_only_fallback_never_shows_summary_failure(monkeypatch):
    svc.SUMMARY_CACHE.clear()
    monkeypatch.setattr(svc, "_safe_fetch_html", lambda url: (_ for _ in ()).throw(RuntimeError("paywall")))
    monkeypatch.setattr(svc, "_translate_ko", lambda text: ("엔비디아, 차세대 AI 칩 출하 확대", True))

    result = svc._build_summary(
        "https://example.com/news/title-only",
        "Nvidia expands next-generation AI chip shipments",
        "",
    )
    assert result["basis"] == "headline_only"
    assert result["basisLabel"] == "제목 기반"
    assert result["summary"].startswith("제목 기준 · ")
    assert "만들지 못했습니다" not in result["summary"]


def test_translation_failure_never_leaves_english_summary_cached(monkeypatch):
    svc.SUMMARY_CACHE.clear()
    monkeypatch.setattr(svc, "_safe_fetch_html", lambda url: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(svc, "_translate_ko", lambda text: (_ for _ in ()).throw(RuntimeError("translate unavailable")))

    result = svc._build_summary(
        "https://example.com/news/translate-fail",
        "Memory demand remains strong",
        "AI memory demand remains strong and the company expects shipments to rise next quarter.",
    )
    assert result["basis"] == "provider_snippet"
    assert "한국어 번역" in result["summary"]
    assert result["translationError"] == "summary_translation_failed"
    assert svc.SUMMARY_CACHE == {}


def test_cache_key_changes_when_translation_pipeline_version_changes(monkeypatch):
    first = svc._cache_key("https://example.com/a", "Title", "Snippet")
    monkeypatch.setattr(svc, "SUMMARY_CACHE_VERSION", "different")
    second = svc._cache_key("https://example.com/a", "Title", "Snippet")
    assert first != second


def test_frontend_does_not_generate_title_only_summary():
    js = (ROOT / "static/js/news_readability_v41_2.js").read_text(encoding="utf-8")
    assert "/api/news-summary" in js
    assert "기사 본문을 읽고 한국어로 요약" in js
    assert "oneLineSummary(title.textContent)" not in js


def test_summary_router_is_wired():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "news_summary_router_v43" in main
    assert "app.include_router(news_summary_router_v43)" in main
