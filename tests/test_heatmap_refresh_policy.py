from heatmap_refresh_policy import needs_refresh

def test_partial_and_failed_refreshes_cannot_restart_on_every_poll():
    partial = {'results': [{'ticker': 'AAPL'}], 'complete': False}
    cache = {'timestamp': 1000, 'lastAttempt': 1000}
    for now in (1001, 1003, 1015, 1059):
        assert not needs_refresh(partial, cache, now)
        assert not needs_refresh(None, {'lastAttempt': 1000}, now)
    assert needs_refresh(partial, cache, 1060)
    assert needs_refresh(None, {'lastAttempt': 1000}, 1060)

def test_seed_is_immediate_but_complete_snapshot_is_shared_for_five_minutes():
    assert needs_refresh({'complete': False}, {'timestamp': 0}, 1000)
    assert not needs_refresh({'complete': True}, {'timestamp': 1000}, 1299)
    assert needs_refresh({'complete': True}, {'timestamp': 1000}, 1300)
