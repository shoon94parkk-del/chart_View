from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_detail_navigation_has_no_global_visibility_observer():
    vis=(ROOT/'static/js/detail_visibility_v40_1.js').read_text(encoding='utf-8')
    nav=(ROOT/'static/js/ux_v3.js').read_text(encoding='utf-8')
    assert 'observer.observe(document.body' not in vis
    assert 'observer.observe(document.documentElement' not in vis
    assert 'navigateUserTab' in nav and '__closeStockDetail' in nav and 'history.replaceState' in nav

def test_news_state_is_event_driven_and_no_html_snapshot_restore():
    hub=(ROOT/'static/js/my_hub_v41.js').read_text(encoding='utf-8')
    resilience=(ROOT/'static/js/resilience_v41_3.js').read_text(encoding='utf-8')
    assert 'receivedAt' in hub and 'lastSuccessKey' in hub and 'chartview:v41-news-state' in hub
    assert 'relatedSymbols' in hub and 'relations' in hub
    assert 'feedSnapshot' not in resilience and 'feed.innerHTML = feedSnapshot' not in resilience
    assert 'MutationObserver' not in resilience
    assert 'chartview:v41-news-state' in resilience

def test_relation_and_chart_readability_contracts():
    service=(ROOT/'news_service_v37.py').read_text(encoding='utf-8')
    detail=(ROOT/'static/js/single_detail_v40.js').read_text(encoding='utf-8')
    assert '_relation_meta' in service and 'relationType' in service and 'relationBasis' in service
    assert '조정주가' in detail and 'data-detail-chart-readout' in detail and 'ArrowLeft' in detail and 'detail-v42-zero' in detail
