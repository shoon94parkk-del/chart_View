from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_news_readability_assets_and_markers_are_loaded():
    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    js = (ROOT / 'static/js/news_readability_v41_2.js').read_text(encoding='utf-8')
    assert '/static/css/news_readability_v41_2.css?v=' in boot
    assert '/static/js/news_readability_v41_2.js?v=' in boot
    assert "newsReadability = 'v49'" in js
    assert 'syncSummaryExpansion' in js
    assert "setProperty(property, value, 'important')" in js


def test_summary_and_market_context_contract():
    js = (ROOT / 'static/js/news_readability_v41_2.js').read_text(encoding='utf-8')
    css = (ROOT / 'static/css/news_readability_v41_2.css').read_text(encoding='utf-8')
    for text in ('한줄 요약', '본문 확인 중', '기사 본문을 읽고 한국어로 요약', '/api/news-summary', '최근 2거래일 반등', '최근 2거래일 약세', '기간 고점권', '기간 저점권', '5거래일 전', '현재'):
        assert text in js
    assert '제목 기준 핵심' not in js
    assert 'oneLineSummary(title.textContent)' not in js
    assert "chartview:v41-news-rendered" in js
    assert "slice(0, 69)" not in js
    assert 'observer.observe(document.documentElement' not in js
    assert '.news-v412-summary.is-expanded' in css