from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_news_summary_is_expandable_and_cache_busted():
    js = (ROOT / "static/js/news_readability_v41_2.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/news_readability_v41_2.css").read_text(encoding="utf-8")
    boot = (ROOT / "static/js/home_watchlist_boot_v32c.js").read_text(encoding="utf-8")
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert "document.createElement('button')" in js
    assert "aria-expanded" in js
    assert "본문 요약 전체보기" in js
    assert "기사 본문을 읽고 한국어로 요약" in js
    assert "/api/news-summary" in js
    assert "SUMMARY_CONCURRENCY = 3" in js
    assert "news-v417-summary-text" in js
    assert ".news-v412-summary.is-expanded .news-v417-summary-text" in css
    assert "-webkit-line-clamp:2" in css
    assert "slice(0, 69)" not in js
    assert "oneLineSummary(title.textContent)" not in js
    assert "chartview:v41-news-rendered" in js
    assert "news_readability_v41_2.css?v=" in boot
    assert "news_readability_v41_2.js?v=" in boot
    assert "home_watchlist_boot_v32c.js?v=" in html
