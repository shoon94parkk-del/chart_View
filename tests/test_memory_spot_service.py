import asyncio

import memory_spot_service as service
from memory_spot_service import NAND_SOURCE_URL, _merge_group_results, _merge_history, _parse_public_page, parse_trendforce_dram_spot


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
    monkeypatch.setattr(service, "_read_publication", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    service._cache["payload"] = None
    service._cache["timestamp"] = 0.0

    first, _ = asyncio.run(service._latest_payload())
    second, cache_hit = asyncio.run(service._latest_payload())

    assert first["stale"] is True
    assert second["stale"] is True
    assert cache_hit is True
    assert calls["count"] == 1


NAND_SAMPLE = """
<html><body>
<div>NAND Flash Spot Price</div>
<div>Last Update 2026-09-21 14:40 (GMT+8)</div>
<table>
<tr><th>Item</th><th>Daily High</th><th>Daily Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Session Change</th></tr>
<tr><td>SLC 2Gb 256MBx8</td><td>4.55</td><td>4.18</td><td>4.55</td><td>4.18</td><td>4.345</td><td>▲ 0.51 %</td></tr>
<tr><td>SLC 1Gb 128MBx8</td><td>3.65</td><td>2.90</td><td>3.65</td><td>2.90</td><td>3.358</td><td>— 0.00 %</td></tr>
<tr><td>MLC 64Gb 8GBx8</td><td>53.50</td><td>35.00</td><td>53.50</td><td>35.00</td><td>40.75</td><td>▲ 2.10 %</td></tr>
<tr><td>MLC 32Gb 4GBx8</td><td>21.20</td><td>18.70</td><td>21.20</td><td>18.70</td><td>19.30</td><td>▲ 1.40 %</td></tr>
</table>
<div>Wafer Spot Price</div>
<div>Last Update 2026-09-21 14:40 (GMT+8)</div>
<table>
<tr><th>Item</th><th>Weekly High</th><th>Weekly Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Session Change</th></tr>
<tr><td>512Gb TLC</td><td>22.00</td><td>17.50</td><td>22.00</td><td>17.50</td><td>19.883</td><td>▼ -1.00 %</td></tr>
<tr><td>256Gb TLC</td><td>20.00</td><td>16.00</td><td>20.00</td><td>16.00</td><td>17.885</td><td>▲ 6.41 %</td></tr>
<tr><td>128Gb TLC</td><td>15.00</td><td>8.00</td><td>15.00</td><td>8.00</td><td>9.967</td><td>— 0.00 %</td></tr>
</table>
</body></html>
"""


def test_parse_nand_chip_and_wafer_groups():
    payload = _parse_public_page(NAND_SAMPLE, NAND_SOURCE_URL)
    groups = {group["key"]: group for group in payload["groups"]}
    assert set(groups) == {"nand-chip", "nand-wafer"}
    assert groups["nand-chip"]["sourceDate"] == "2026-09-21"
    assert groups["nand-chip"]["items"][2]["average"] == 40.75
    assert groups["nand-wafer"]["items"][0]["average"] == 19.883
    assert groups["nand-wafer"]["items"][1]["changePct"] == 6.41


def test_catalog_marks_non_public_hbm_mcp_prices_without_fabricating_values():
    payload = _merge_group_results([], {})
    unavailable = {row["key"]: row["reason"] for row in payload["unavailablePriceSeries"]}
    assert "hbm" in unavailable
    assert "mcp" in unavailable
    assert "emmc-ufs" in unavailable
    assert all("가격" in reason or "수치" in reason for reason in unavailable.values())


def test_gddr_label_whitespace_keeps_chip_density_and_matches_public_row():
    html = '''<div>Last Update 2026-11-10 18:10 (GMT+8)</div><table>
    <tr><td>GDDR6  8Gb</td><td>13</td><td>11</td><td>13</td><td>11</td><td>12</td><td>0%</td></tr>
    <tr><td>GDDR6 8GB</td><td>99</td><td>99</td><td>99</td><td>99</td><td>99</td><td>0%</td></tr>
    </table>'''
    group = _parse_public_page(html, service.DRAM_SOURCE_URL)["groups"][0]
    assert [(row["key"], row["average"]) for row in group["items"]] == [("gddr6-8gb", 12)]


def test_scheduled_publication_bypasses_provider_and_six_hour_cache(monkeypatch):
    payload = {**_merge_group_results([], {}), "generatedAt": "2026-11-10T10:35:00Z", "history": []}
    monkeypatch.setattr(service, "_read_publication", lambda: (payload, "github-main"))
    monkeypatch.setattr(service, "_cache", {"payload": {"generatedAt": "2026-11-09T10:35:00Z"}, "timestamp": service.time.time()})
    monkeypatch.setattr(service, "_fetch_latest_sync", lambda: (_ for _ in ()).throw(AssertionError("visitor must not scrape")))
    result, hit = asyncio.run(service._latest_payload())
    assert result["generatedAt"] == "2026-11-10T10:35:00Z"
    assert result["publicationSource"] == "github-main"
    assert result["collectionMode"] == "scheduled"
    assert hit is False
    _, hit = asyncio.run(service._latest_payload())
    assert hit is True


def test_restart_restores_full_published_history_without_redis(monkeypatch):
    async def no_redis():
        return None
    monkeypatch.setattr(service, "_get_redis", no_redis)
    monkeypatch.setattr(service, "_memory_history", [])
    latest = {"groups": [], "history": [{"date": "2026-11-09", "values": {"ddr5-16gb": 0.0}}]}
    history, storage = asyncio.run(service._load_history(latest))
    assert next(row for row in history if row["date"] == "2026-11-09")["values"]["ddr5-16gb"] == 0.0
    assert storage == "github-publication+memory"


def test_empty_redis_restores_all_published_dates(monkeypatch):
    class Redis:
        saved = None
        async def get(self, _key):
            return None
        async def set(self, _key, value, **_kwargs):
            self.saved = service.json.loads(value)
    redis = Redis()
    async def get_redis():
        return redis
    monkeypatch.setattr(service, "_get_redis", get_redis)
    latest = {"groups": [], "history": [
        {"date": "2026-11-06", "values": {"ddr5-16gb": 60.0}},
        {"date": "2026-11-09", "values": {"ddr5-16gb": 61.0}},
    ]}
    history, storage = asyncio.run(service._load_history(latest))
    assert {"2026-11-06", "2026-11-09"} <= {row["date"] for row in history}
    assert redis.saved == history
    assert storage == "github-publication+render-key-value"


def test_both_api_aliases_serve_scheduled_history_without_scraping(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    payload = {**_merge_group_results([], {}), "generatedAt": "2026-11-10T10:35:00Z",
               "history": [{"date": "2026-11-09", "values": {"ddr5-16gb": 60.0}}]}
    monkeypatch.setattr(service, "_read_publication", lambda: (payload, "github-main"))
    monkeypatch.setattr(service, "_fetch_latest_sync", lambda: (_ for _ in ()).throw(AssertionError("visitor must not scrape")))
    async def no_redis():
        return None
    monkeypatch.setattr(service, "_get_redis", no_redis)
    monkeypatch.setattr(service, "_memory_history", [])
    app = FastAPI()
    app.include_router(service.router)
    with TestClient(app) as client:
        for route in ["/api/memory-prices", "/api/memory-spot"]:
            response = client.get(route)
            data = response.json()
            assert response.status_code == 200
            assert data["schemaVersion"] == 2
            assert len(data["groups"]) == 5
            assert len(data["items"]) == 3
            assert data["collectionMode"] == "scheduled"
            assert any(row["date"] == "2026-11-09" for row in data["history"])
            assert "max-age=60" in response.headers["cache-control"]
