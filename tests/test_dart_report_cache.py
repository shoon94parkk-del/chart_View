import json
import time

import dart_business_service as dart


def test_official_hanwha_and_dongseong_reports_are_precomputed():
    for code in ("042660", "033500"):
        row = dart._static_business_context(code)
        assert row is not None and row["available"] is True
        assert row["topItem"]["share"] > 0


def _row(receipt="20260310002820"):
    return {
        "available": True, "stockCode": "005930", "ticker": "005930.KS",
        "rceptNo": receipt, "reportYear": 2025,
        "topItem": {"name": "DX", "share": 56.3},
    }


def test_validated_static_report_remains_usable_after_fourteen_days(tmp_path, monkeypatch):
    path = tmp_path / "dart.json"
    path.write_text(json.dumps({
        "updated": "2025-01-01T00:00:00+09:00",
        "companies": {"005930": _row()},
    }), encoding="utf-8")
    monkeypatch.setattr(dart, "BUSINESS_CONTEXT_CACHE_PATH", str(path))
    monkeypatch.setattr(dart, "_STATIC_BUSINESS_CONTEXT", (0.0, {}))
    monkeypatch.delenv("DART_STATIC_CACHE_BYPASS", raising=False)
    assert dart._static_business_context("005930")["rceptNo"] == "20260310002820"


def test_persistent_cache_reuses_validated_receipt_after_process_memory_clears(monkeypatch):
    stored = {}

    class RedisStub:
        def get(self, key):
            return stored.get(key)

        def set(self, key, value):
            stored[key] = value

    monkeypatch.setattr(dart, "_redis_client", lambda: RedisStub())
    monkeypatch.setattr(dart, "_static_business_context", lambda code: None)
    monkeypatch.setattr(dart, "_schedule_report_check", lambda *args: None)
    monkeypatch.delenv("DART_STATIC_CACHE_BYPASS", raising=False)
    with dart._CACHE_LOCK:
        dart._CACHE.clear()
    dart._save_persistent("005930", _row(), time.time())
    assert dart.fetch_business_report("005930.KS")["cacheMode"] == "render-key-value"
    with dart._CACHE_LOCK:
        dart._CACHE.clear()
    assert dart.fetch_business_report("005930.KS")["rceptNo"] == "20260310002820"


def test_revalidated_static_row_wins_over_older_parser_output_for_same_receipt(monkeypatch):
    old = dict(_row(), topItem={"name": "PU 단열재 사 업 부 문", "share": 96.2})
    current = dict(_row(), topItem={"name": "PU 단열재 사업부문", "share": 96.2})
    monkeypatch.setattr(dart, "_load_persistent", lambda code: (time.time(), old))
    monkeypatch.setattr(dart, "_static_business_context", lambda code: current)
    monkeypatch.setattr(dart, "_schedule_report_check", lambda *args: None)
    monkeypatch.delenv("DART_STATIC_CACHE_BYPASS", raising=False)
    with dart._CACHE_LOCK:
        dart._CACHE.clear()
    result = dart.fetch_business_report("005930.KS")
    assert result["cacheMode"] == "static-precomputed"
    assert result["topItem"]["name"] == "PU 단열재 사업부문"


def test_receipt_check_skips_parsing_unchanged_report(monkeypatch):
    old = _row()
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(dart, "_search_report_api", lambda key, code: {"rceptNo": old["rceptNo"]})
    monkeypatch.setattr(dart, "fetch_business_report", lambda *a, **k: (_ for _ in ()).throw(AssertionError("parsed unchanged report")))
    monkeypatch.setattr(dart, "_save_persistent", lambda *a: None)
    dart._refresh_cached_report("005930", "005930.KS", "삼성전자", old)
    assert dart._CACHE["005930"][1]["rceptNo"] == old["rceptNo"]


def test_failed_new_receipt_keeps_last_validated_report(monkeypatch):
    old = _row()
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(dart, "_search_report_api", lambda key, code: {"rceptNo": "20270401000001"})
    monkeypatch.setattr(dart, "fetch_business_report", lambda *a, **k: {"available": False})
    dart._refresh_cached_report("005930", "005930.KS", "삼성전자", old)
    assert dart._CACHE["005930"][1] == old
