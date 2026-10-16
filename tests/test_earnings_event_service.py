from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

import earnings_event_service as service


NOW = datetime(2026, 10, 16, 2, tzinfo=timezone.utc)


def official_event():
    return {
        "id": "AAPL:earnings_call:2026-11-02T22:00:00Z",
        "symbol": "AAPL", "name": "Apple", "title": "FY26 Q4 results conference call",
        "eventType": "earnings_call", "timingRole": "conference_call",
        "scheduledAt": "2026-11-02T22:00:00Z", "timezone": "America/New_York",
        "publishedAt": None,
        "source": {
            "name": "Apple Investor Relations", "url": "https://investor.apple.com/investor-relations/default.aspx",
            "evidenceUrl": "https://investor.apple.com/rss/Event.aspx?LanguageId=1",
            "publishedAt": "2026-10-06T21:09:11Z", "checkedAt": "2026-10-16T01:52:05Z",
            "contentSha256": "a" * 64,
        },
    }


def cache_file(tmp_path, event=None, **overrides):
    payload = {
        "schemaVersion": "earnings-events-v1", "generatedAt": "2026-10-16T01:55:00Z",
        "sources": {"AAPL": {"status": "ok", "checkedAt": "2026-10-16T01:52:05Z"}},
        "events": [official_event() if event is None else event],
    }
    payload.update(overrides)
    path = tmp_path / "events.json"
    path.write_text(json.dumps(payload))
    return path


def test_official_call_keeps_source_publication_separate_from_results(tmp_path):
    payload = service.get_earnings_events("aapl", now=NOW, cache_path=cache_file(tmp_path))
    row = payload["events"][0]
    assert row["scheduledAt"] == "2026-11-02T22:00:00Z"
    assert row["scheduledAtKst"] == "2026-11-03T07:00:00+09:00"
    assert (row["localDate"], row["localTime"], row["timezone"]) == ("2026-11-02", "17:00", "America/New_York")
    assert row["timingRole"] == "conference_call"
    assert row["publishedAt"] is None
    assert row["source"]["publishedAt"] == "2026-10-06T21:09:11Z"
    assert row["session"] == "unknown"
    assert payload["comparison"]["status"] == "unavailable"
    assert "surprisePercent" not in row and "epsActual" not in row


def test_expired_calls_are_not_presented_as_next_events(tmp_path):
    later = datetime(2026, 11, 3, tzinfo=timezone.utc)
    payload = service.get_earnings_events("AAPL", now=later, cache_path=cache_file(tmp_path))
    assert payload["events"] == []
    assert payload["coverage"]["missing"][0]["reason"] == "no_upcoming_verified_call"


def test_stale_source_is_not_restamped_or_shown_as_current_schedule(tmp_path):
    event = official_event()
    event["source"]["checkedAt"] = "2026-10-08T01:00:00Z"
    payload = service.get_earnings_events("AAPL", now=NOW, cache_path=cache_file(tmp_path, event))
    assert payload["events"] == []
    assert payload["coverage"]["missing"][0]["reason"] == "source_check_stale"
    assert payload["coverage"]["missing"][0]["checkedAt"] == "2026-10-08T01:00:00Z"


@pytest.mark.parametrize("change", [
    {"scheduledAt": "2026-11-02"},
    {"scheduledAt": "2026-11-02T17:00:00"},
    {"timezone": "Invalid/Zone"},
    {"eventType": "earnings_release"},
    {"publishedAt": "2026-11-02T22:00:00Z"},
])
def test_unverified_release_semantics_or_naive_times_fail_closed(tmp_path, change):
    event = official_event()
    event.update(change)
    payload = service.get_earnings_events("AAPL", now=NOW, cache_path=cache_file(tmp_path, event))
    assert payload["events"] == []


def test_official_source_host_and_observed_time_are_required(tmp_path):
    for field, value in [("url", "https://investor.apple.com.evil.example/a"), ("checkedAt", None), ("checkedAt", "2026-11-01T00:00:00Z")]:
        event = official_event()
        event["source"][field] = value
        payload = service.get_earnings_events("AAPL", now=NOW, cache_path=cache_file(tmp_path, event))
        assert payload["events"] == []


def test_provider_free_missing_cache_and_unsupported_symbol(tmp_path):
    missing = service.get_earnings_events("MSFT", now=NOW, cache_path=tmp_path / "missing.json")
    assert missing["events"] == []
    assert missing["coverage"]["missing"][0]["reason"] == "issuer_not_covered"
    assert missing["cacheMode"] == "static"


def test_rows_are_sorted_and_deduplicated_without_mutating_cache(tmp_path):
    first = official_event()
    second = deepcopy(first)
    second.update(id="AAPL:later", scheduledAt="2026-11-04T22:00:00Z")
    path = cache_file(tmp_path, events=[second, first, deepcopy(first)])
    payload = service.get_earnings_events(now=NOW, cache_path=path)
    assert [x["id"] for x in payload["events"]] == [first["id"], second["id"]]
    assert "scheduledAtKst" not in json.loads(path.read_text())["events"][0]
