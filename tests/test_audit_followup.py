import news_service_v37 as news

def test_provider_tag_alone_is_not_evidence():
    assert news._relation_meta('Core & Main profits rise', 'Buybacks and acquisitions', '엔비디아', 'NVDA')[0] == 'unverified'

def test_english_company_alias_is_direct():
    assert news._relation_meta('NVIDIA announces new GPUs', '', '엔비디아', 'NVDA')[0] == 'direct'

def test_explicit_sector_is_related_with_reason():
    kind, reason = news._relation_meta('HBM supply tightens', '', '엔비디아', 'NVDA')
    assert kind == 'related'
    assert 'HBM' in reason.upper()
