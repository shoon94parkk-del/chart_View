"""Offline safety checks for canonical warm seed, timestamps and bounded capture."""
import copy
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from heatmap_snapshot import (SnapshotValidationError, eligible_markets, load_snapshot,
                              merge_seed_rows, validate_snapshot)
from heatmap_refresh_policy import needs_refresh

NOW = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
ELIGIBLE = {"005930.KS": "KR", "AAPL": "US"}


def quote(ticker, market, **changes):
    row = {"ticker": ticker, "market": market, "name": ticker, "price": 100,
           "change": -1.25, "marketCap": 1000, "asOf": "2026-10-06T20:00:00+00:00",
           "sessionDate": "2026-10-06", "previousSessionDate": "2026-10-05",
           "source": "Naver Finance KRX/Koscom" if market == "KR" else "Yahoo Chart regularMarketPrice + official previousClose",
           "quoteBasis": "provider-canonical", "stale": False}
    return {**row, **changes}


def snapshot(**changes):
    rows = [quote("005930.KS", "KR"), quote("AAPL", "US")]
    return {"snapshotVersion": 1, "snapshotCapturedAt": NOW.isoformat(),
            "generatedAt": (NOW - timedelta(minutes=5)).isoformat(),
            "source": "canonical-provider-full-heatmap", "results": rows,
            "counts": {"KR": 1, "US": 1}, "complete": True, **changes}


def test_valid_seed_preserves_every_price_date_and_provider_but_is_stale():
    payload = snapshot()
    before = copy.deepcopy(payload)
    result = validate_snapshot(payload, ELIGIBLE, now=NOW, require_complete=True)
    assert payload == before
    assert result["generatedAt"] == before["generatedAt"]
    for original, seeded in zip(before["results"], result["results"]):
        assert seeded == {**original, "stale": True}
    assert needs_refresh(result, {"timestamp": 0}, NOW.timestamp())


@pytest.mark.parametrize("field,value", [
    ("price", None), ("price", 0), ("price", -1), ("price", "100"), ("price", True),
    ("change", None), ("change", ""), ("change", float("nan")),
    ("change", float("inf")), ("marketCap", float("-inf")),
    ("asOf", None), ("asOf", "2026-10-06"), ("asOf", "bad-date"),
    ("asOf", "2026-10-08T00:00:00Z"), ("sessionDate", "2026-10-08"),
    ("previousSessionDate", "2026-10-06"), ("previousSessionDate", "not-a-date"),
    ("source", None), ("source", "legacy heatmap.json"), ("quoteBasis", "daily-cache"),
    ("market", "KR"), ("stale", "false"),
])
def test_one_invalid_row_invalidates_the_whole_snapshot(field, value):
    payload = snapshot()
    payload["results"][1][field] = value
    with pytest.raises(SnapshotValidationError):
        validate_snapshot(payload, ELIGIBLE, now=NOW)


@pytest.mark.parametrize("field", ["generatedAt", "snapshotCapturedAt"])
@pytest.mark.parametrize("instant", [NOW + timedelta(seconds=1), NOW - timedelta(hours=48, seconds=1)])
def test_future_or_expired_container_cannot_extend_dates(field, instant):
    with pytest.raises(SnapshotValidationError):
        validate_snapshot(snapshot(**{field: instant.isoformat()}), ELIGIBLE, now=NOW)


def test_old_individual_observation_is_removed_without_discarding_recent_rows():
    payload = snapshot()
    payload["results"][1].update(asOf="2026-10-05T14:59:59Z", sessionDate="2026-10-05", previousSessionDate="2026-10-02")
    result = validate_snapshot(payload, ELIGIBLE, now=NOW)
    assert [row["ticker"] for row in result["results"]] == ["005930.KS"]
    assert result["counts"] == {"KR": 1, "US": 0}
    assert result["complete"] is False
    with pytest.raises(SnapshotValidationError):
        validate_snapshot(payload, ELIGIBLE, now=NOW, require_complete=True)


def test_changed_universe_intersection_does_not_use_legacy_metadata_quotes():
    payload = snapshot()
    result = validate_snapshot(payload, {"005930.KS": "KR", "MSFT": "US"}, now=NOW)
    assert [row["ticker"] for row in result["results"]] == ["005930.KS"]
    assert eligible_markets(["005930.KS"], [{"ticker": "MSFT", "price": 1, "change": 99}]) == {"005930.KS": "KR", "MSFT": "US"}
    payload["results"][1]["price"] = None
    with pytest.raises(SnapshotValidationError):
        validate_snapshot(payload, {"005930.KS": "KR"}, now=NOW)


@pytest.mark.parametrize("change", [{"snapshotVersion": True}, {"counts": {"KR": True, "US": 1}},
                                    {"counts": {"KR": 20, "US": 40}}, {"source": "legacy-layout"}])
def test_bad_envelope_fails_closed(change):
    with pytest.raises(SnapshotValidationError):
        validate_snapshot(snapshot(**change), ELIGIBLE, now=NOW)


def test_duplicate_rows_cannot_fake_complete_coverage():
    payload = snapshot()
    payload["results"].append(copy.deepcopy(payload["results"][0]))
    payload["counts"]["KR"] = 2
    with pytest.raises(SnapshotValidationError):
        validate_snapshot(payload, ELIGIBLE, now=NOW)


def test_invalid_missing_or_oversize_file_preserves_existing_fallback(tmp_path):
    path = tmp_path / "snapshot.json"
    assert load_snapshot(path, ELIGIBLE, now=NOW) is None
    path.write_text("{malformed", encoding="utf-8")
    assert load_snapshot(path, ELIGIBLE, now=NOW) is None
    path.write_text(" " * (1024 * 1024 + 1), encoding="utf-8")
    assert load_snapshot(path, ELIGIBLE, now=NOW) is None
    path.write_text(json.dumps(snapshot()), encoding="utf-8")
    assert len(load_snapshot(path, ELIGIBLE, now=NOW)["results"]) == 2


def test_newer_home_and_cache_quotes_win_and_equal_dates_prefer_current():
    seeded = validate_snapshot(snapshot(), ELIGIBLE, now=NOW)["results"]
    current = quote("AAPL", "US", price=200, asOf="2026-10-07T14:00:00Z", sessionDate="2026-10-07", quoteBasis="home-canonical")
    cached = quote("AAPL", "US", price=150, asOf="2026-10-07T13:00:00Z", sessionDate="2026-10-07")
    result = merge_seed_rows(seeded, [current, cached], ELIGIBLE)
    assert result[1] == current
    equal = quote("AAPL", "US", price=300, quoteBasis="home-canonical")
    assert merge_seed_rows(seeded, [equal], ELIGIBLE)[1] == equal


def test_older_snapshot_cannot_replace_unknown_observation_from_current_home():
    seeded = validate_snapshot(snapshot(), ELIGIBLE, now=NOW)["results"]
    current = quote("AAPL", "US", price=200, asOf=None, quoteBasis="home-canonical")
    assert merge_seed_rows(seeded, [current], ELIGIBLE)[1] == current


def test_recent_snapshot_replaces_older_canonical_or_daily_cache_but_is_never_fresh():
    seeded = validate_snapshot(snapshot(), ELIGIBLE, now=NOW)["results"]
    older = quote("AAPL", "US", price=1, asOf="2026-10-05T20:00:00Z", sessionDate="2026-10-05", previousSessionDate="2026-10-02")
    result = merge_seed_rows(seeded, [older], ELIGIBLE)
    assert result[1]["price"] == 100 and result[1]["stale"] is True
    daily = quote("005930.KS", "KR", price=1, asOf="2026-10-06", quoteBasis="daily-cache")
    assert merge_seed_rows(seeded, [daily], ELIGIBLE)[0] == seeded[0]


def capture_module():
    path = Path(__file__).resolve().parents[1] / "scripts/save_full_heatmap_snapshot.py"
    spec = importlib.util.spec_from_file_location("save_full_heatmap_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield json.dumps(self.payload).encode()


class Session:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.payload)


def test_capture_one_normal_request_keeps_api_values_and_atomically_saves(tmp_path):
    module = capture_module()
    payload = snapshot(snapshotCapturedAt=datetime.now(timezone.utc).isoformat(), generatedAt=datetime.now(timezone.utc).isoformat())
    # Use fresh observations rather than fixture wall-clock age.
    for row in payload["results"]:
        row.update(asOf=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), sessionDate=None, previousSessionDate=None)
    session, output = Session(payload), tmp_path / "full.json"
    result = module.save_snapshot("https://example.test", output, session=session, eligible=ELIGIBLE)
    assert len(session.calls) == 1
    url, options = session.calls[0]
    assert url == "https://example.test/api/heatmap/full"
    assert "params" not in options and "verify" not in options and options["allow_redirects"] is False
    assert result["results"] == payload["results"]
    assert json.loads(output.read_text())["generatedAt"] == payload["generatedAt"]
    assert not output.with_name("full.json.tmp").exists()


def test_capture_partial_invalid_response_keeps_old_file_and_caps_requests(tmp_path):
    module = capture_module()
    output = tmp_path / "full.json"
    output.write_text("previous verified snapshot")
    session = Session({"results": []})
    with pytest.raises(SnapshotValidationError):
        module.save_snapshot("https://example.test", output, attempts=3, session=session, eligible=ELIGIBLE)
    assert len(session.calls) == 3
    assert output.read_text() == "previous verified snapshot"
    with pytest.raises(ValueError):
        module.save_snapshot("https://example.test", output, attempts=4, session=session, eligible=ELIGIBLE)
    with pytest.raises(ValueError):
        module.save_snapshot("https://example.test?fresh=true", output, session=session, eligible=ELIGIBLE)


def test_capture_eligible_universe_matches_existing_20_40_contract():
    universe = capture_module().current_eligible()
    assert sum(value == "KR" for value in universe.values()) == 20
    assert sum(value == "US" for value in universe.values()) == 40


def test_app_cold_seed_fills_all_40_immediately_without_provider_or_fresh_timestamp():
    import main
    us_rows = [{"ticker": f"US{index}", "name": f"US{index}", "market": "US", "marketCap": 1000} for index in range(40)]
    validated = {"generatedAt": "2026-10-06T20:00:00Z", "snapshotCapturedAt": "2026-10-07T14:00:00Z",
                 "results": [quote(row["ticker"], "US", stale=True) for row in us_rows]}
    home = {"US0": quote("US0", "US", price=200, asOf="2026-10-07T14:30:00Z", sessionDate="2026-10-07", quoteBasis="home-canonical")}
    cache = {"data": None, "timestamp": 999, "refreshing": False}
    with patch.object(main, "FULL_HEATMAP_CACHE", cache), \
         patch.object(main, "FULL_HEATMAP_KR_TICKERS", []), \
         patch.object(main, "_load_full_heatmap_us_rows", return_value=us_rows), \
         patch.object(main, "_load_home_insight_sources", return_value={}), \
         patch.object(main, "_home_heatmap_rows_by_ticker", return_value=home), \
         patch.object(main, "load_snapshot", return_value=validated), \
         patch.object(main, "fetch_quote_snapshot") as provider:
        result = main._seed_full_heatmap_from_local()
    provider.assert_not_called()
    assert result["counts"] == {"KR": 0, "US": 40}
    assert result["complete"] is True
    assert result["generatedAt"] == validated["generatedAt"]
    assert result["results"][0]["price"] == 200
    assert sum(row["stale"] for row in result["results"]) == 39
    assert cache["timestamp"] == 0
    assert needs_refresh(result, cache, NOW.timestamp())


def test_app_rejected_snapshot_keeps_existing_home_only_seed_without_legacy_prices():
    import main
    meta = [{"ticker": "AAPL", "market": "US", "marketCap": 1000}, {"ticker": "MSFT", "market": "US", "marketCap": 1000}]
    home = {"AAPL": quote("AAPL", "US", price=200, quoteBasis="home-canonical")}
    with patch.object(main, "FULL_HEATMAP_CACHE", {"data": None, "timestamp": 0}), \
         patch.object(main, "FULL_HEATMAP_KR_TICKERS", []), \
         patch.object(main, "_load_full_heatmap_us_rows", return_value=meta), \
         patch.object(main, "_load_home_insight_sources", return_value={}), \
         patch.object(main, "_home_heatmap_rows_by_ticker", return_value=home), \
         patch.object(main, "load_snapshot", return_value=None):
        result = main._seed_full_heatmap_from_local()
    assert [row["ticker"] for row in result["results"]] == ["AAPL"]
    assert result["results"][0]["price"] == 200
    assert result["source"] == "canonical-seed-no-legacy-quotes"
