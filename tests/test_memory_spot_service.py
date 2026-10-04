import asyncio

import memory_spot_service as service
from memory_spot_service import _merge_history, parse_trendforce_dram_spot


SAMPLE = """
<html><body>
<div>Last Update 2026-10-02 18:10 (GMT+8)</div>
<table>
<tr><th>Item</th><th>Daily High</th><th>Daily Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Session Change</th></tr>
<tr><td>DDR5 16Gb (2Gx8) 4800/5600</td><td>69.50</td><td>43.50</td><td>69.50</td><td>43.50</td><td>58.00</td><td>▲ 0.12 %</td></tr>
<tr><td>DDR5 16Gb (2Gx8) eTT</td><td>27.80</td><td>25.40</td><td>27.80</td><td>25.40</td><td>26.10</td><td>▲ 0.39 %</td></tr>
<tr><td>DDR4 16Gb (2Gx8) 3200</td><td>118.00</td><td>45.50</td><td>118.00</td><td>45.50</td><td>83.588</td><td>▼ -0.09 %</td></tr>
<tr><td>DDR4 8Gb (1Gx8) 3200</td><td>85.00</td><td>25.00</td><td>85.00</td><td>25.00</td><td>46.321</td><td>— 0.00 %</td></tr>
</table>
</body></html>
"""


def test_parse_public_dram_spot_rows():
    payload = parse_trendforce_dram_spot(SAMPLE)
    assert payload["sourceDate"] == "2026-10-02"
    assert payload["updatedAt"] == "2026-10-02T18:10:00+08:00"
    assert [row["key"] for row in payload["items"]] == [
        "ddr5-16gb",
        "ddr4-16gb",
        "ddr4-8gb",
    ]
    assert payload["items"][0]["average"] == 58.0
    assert payload["items"][1]["changePct"] == -0.09
    assert payload["items"][2]["dailyLow"] == 25.0


def test_merge_history_replaces_same_source_date_without_duplicates():
    latest = parse_trendforce_dram_spot(SAMPLE)
    history = _merge_history(
        [{"date": "2026-10-02", "values": {"ddr4-8gb": 1.0}}],
        latest,
    )
    same_day = [row for row in history if row["date"] == "2026-10-02"]
    assert len(same_day) == 1
    assert same_day[0]["values"]["ddr4-8gb"] == 46.321


def test_failed_fetch_uses_retry_cooldown(monkeypatch):
    calls = {"count": 0}

    def fail():
        calls["count"] += 1
        raise RuntimeError("blocked")

    monkeypatch.setattr(service, "_fetch_latest_sync", fail)
    service._cache["payload"] = None
    service._cache["timestamp"] = 0.0

    first, _ = asyncio.run(service._latest_payload())
    second, cache_hit = asyncio.run(service._latest_payload())

    assert first["stale"] is True
    assert second["stale"] is True
    assert cache_hit is True
    assert calls["count"] == 1
