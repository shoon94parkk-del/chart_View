from profile_sync_service import _normalize_sync_id, _normalize_watchlist


def test_profile_sync_id_is_simple_and_case_insensitive():
    assert _normalize_sync_id(" Park_94 ") == "park_94"


def test_profile_sync_id_rejects_short_or_special_values():
    for value in ("abc", "hello world", "한글아이디", "a" * 33):
        try:
            _normalize_sync_id(value)
        except ValueError:
            pass
        else:
            raise AssertionError(value)


def test_profile_sync_watchlist_dedupes_and_limits_rows():
    rows = [
        {"symbol": "nvda", "name": "엔비디아"},
        {"symbol": "NVDA", "name": "duplicate"},
        {"symbol": "005930.ks", "name": "삼성전자"},
        {"symbol": "<bad>", "name": "bad"},
    ] + [{"symbol": f"T{i}", "name": f"T{i}"} for i in range(30)]
    clean = _normalize_watchlist(rows)
    assert clean[0] == {"symbol": "NVDA", "name": "엔비디아"}
    assert clean[1] == {"symbol": "005930.KS", "name": "삼성전자"}
    assert len(clean) == 20
    assert all("<" not in row["symbol"] for row in clean)
