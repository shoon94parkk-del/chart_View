from datetime import datetime, timezone
import inspect

import main


def test_home_market_windows_are_split_by_exchange_hours():
    kr_open = main._open_home_markets(datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc))
    assert "KR" in kr_open and "US" not in kr_open
    assert len(kr_open["KR"]) == 8

    us_open = main._open_home_markets(datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc))
    assert "US" in us_open and "KR" not in us_open
    assert len(us_open["US"]) == 10


def test_home_live_endpoint_is_memory_only():
    source = inspect.getsource(main.home_live_snapshot)
    assert "fetch_quote_snapshot" not in source
    assert "_home_live_results()" in source
    assert "Render shared memory" in source


def test_background_worker_is_activity_gated():
    source = inspect.getsource(main._home_live_worker)
    assert "active_home > 0" in source
    assert "HOME_LIVE_ACTIVE_REFRESH_SEC" in source
    assert "_refresh_home_live(due)" in source


def test_anonymous_visitor_count_does_not_store_raw_id():
    main.VISITOR_LAST_SEEN.clear()
    main.VISITOR_DAILY.clear()
    raw = "visitor-test-12345678"
    active, active_home = main._record_visitor(raw, "home")
    assert active == 1
    assert active_home == 1
    day = main._today_kst()
    keys = list(main.VISITOR_DAILY[day])
    assert len(keys) == 1
    assert raw not in keys[0]


def test_admin_usage_requires_env_token(monkeypatch):
    monkeypatch.setenv("CHARTVIEW_ADMIN_TOKEN", "secret-test")
    source = inspect.getsource(main._admin_token_ok)
    assert "compare_digest" in source
    assert "X-ChartView-Admin" in source
