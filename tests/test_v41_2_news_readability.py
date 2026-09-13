from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v412_assets_and_markers_are_loaded():
    boot = (ROOT / 'static/js/home_watchlist_boot_v32c.js').read_text(encoding='utf-8')
    assert '/static/css/news_readability_v41_2.css?v=20260913v412' in boot
    assert '/static/js/news_readability_v41_2.js?v=20260913v412' in boot
    assert "home.dataset.newsReadability = 'v41.2'" in boot
    assert "home.dataset.uiVersion = 'v40-stage12'" in boot


def test_v412_summary_and_market_context_contract():
    js = (ROOT / 'static/js/news_readability_v41_2.js').read_text(encoding='utf-8')
    css = (ROOT / 'static/css/news_readability_v41_2.css').read_text(encoding='utf-8')
    for text in ('한줄 요약', '제목 기준', '최근 2거래일 반등', '최근 2거래일 약세', '기간 고점권', '기간 저점권', '5거래일 전', '현재'):
        assert text in js
    assert '.news-v412-summary' in css
    assert '.news-v412-market-metrics' in css
    assert 'width:100%!important' in css
    assert 'height:96px!important' in css
