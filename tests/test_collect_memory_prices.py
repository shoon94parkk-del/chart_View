"""Collector CLI/file boundaries, without public requests or repository writes."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_memory_price_publication import NOW, document, fetched
import memory_spot_service as service

try:
    from scripts import collect_memory_prices as collector
except ImportError:
    collector = SimpleNamespace()


def require(name):
    function = getattr(collector, name, None)
    assert callable(function), f"collector {name} must be implemented"
    return function


def test_collection_seeds_real_api_history_then_preserves_it_after_process_restart(tmp_path, monkeypatch):
    collect = require("collect")
    seed = document()
    seed.pop("generatedAt")
    seed.pop("collectedAt")
    seed_file = tmp_path / "existing-api.json"
    seed_file.write_text(json.dumps(seed), encoding="utf-8")
    original_seed = seed_file.read_bytes()
    output = tmp_path / "nested" / "memory_prices.json"
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: fetched())
    collect(output, seed_history=seed_file, collected_at=NOW)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["history"][-2]["date"] == "2026-11-09"
    assert saved["history"][-2]["values"]["ddr5-16gb"] == 60
    assert saved["history"][-1]["date"] == "2026-11-10"
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: fetched("2026-11-11", average=61))
    collect(output, collected_at="2026-11-11T10:35:00Z")
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert [row["date"] for row in saved["history"]][-3:] == ["2026-11-09", "2026-11-10", "2026-11-11"]
    assert seed_file.read_bytes() == original_seed


def test_all_source_failure_preserves_output_bytes(tmp_path, monkeypatch):
    collect = require("collect")
    output = tmp_path / "memory_prices.json"
    output.write_text(json.dumps(document()), encoding="utf-8")
    before = output.read_bytes()
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: service._merge_group_results([], {
        service.DRAM_SOURCE_URL: "ReadTimeout", service.NAND_SOURCE_URL: "ReadTimeout",
    }))
    with pytest.raises(ValueError, match="all memory"):
        collect(output, collected_at=NOW)
    assert output.read_bytes() == before


def test_invalid_existing_publication_does_not_fetch_or_write(tmp_path, monkeypatch):
    collect = require("collect")
    output = tmp_path / "memory_prices.json"
    output.write_text('{"history": []}', encoding="utf-8")
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: pytest.fail("invalid saved data must fail before fetching"))
    with pytest.raises(ValueError):
        collect(output, collected_at=NOW)
    assert output.read_text(encoding="utf-8") == '{"history": []}'


def test_atomic_replace_failure_preserves_output_and_removes_temporary_file(tmp_path, monkeypatch):
    collect = require("collect")
    output = tmp_path / "memory_prices.json"
    output.write_text(json.dumps(document()), encoding="utf-8")
    before = output.read_bytes()
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: fetched())
    def fail_replace(*_args):
        raise OSError("disk replace failed")
    monkeypatch.setattr(collector.os, "replace", fail_replace)
    with pytest.raises(OSError):
        collect(output, collected_at=NOW)
    assert output.read_bytes() == before
    assert list(tmp_path.iterdir()) == [output]


def test_check_only_validates_without_fetch_or_file_mutation(tmp_path, monkeypatch):
    main = require("main")
    output = tmp_path / "memory_prices.json"
    output.write_text(json.dumps(document()), encoding="utf-8")
    before = output.read_bytes()
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: pytest.fail("--check must not fetch"))
    assert main(["--output", str(output), "--check"]) == 0
    assert output.read_bytes() == before
    output.write_text("{}", encoding="utf-8")
    assert main(["--output", str(output), "--check"]) == 1


def test_duplicate_json_fields_or_nonstandard_numbers_fail_before_fetching(tmp_path, monkeypatch):
    collect = require("collect")
    output = tmp_path / "memory_prices.json"
    monkeypatch.setattr(collector, "_fetch_latest_sync", lambda: pytest.fail("invalid JSON must not fetch"))
    for content in ['{"schemaVersion":2,"schemaVersion":2}', '{"unknown":NaN}']:
        output.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            collect(output, collected_at=NOW)
        assert output.read_text(encoding="utf-8") == content


def test_workflow_runs_direct_collector_at_two_kst_evening_times_with_bounded_serial_push():
    path = Path(__file__).parents[1] / ".github/workflows/update-memory-prices.yml"
    assert path.is_file(), "scheduled memory collection workflow must exist"
    # Validate the emitted shell as code as well as checking the schedule/access boundary.
    import re
    import textwrap
    text = path.read_text(encoding="utf-8")
    assert re.findall(r"^\s+- cron: '([^']+)'$", text, re.MULTILINE) == ["35 10,11 * * *"]
    assert re.search(r"^  workflow_dispatch:$", text, re.MULTILINE)
    assert "permissions:\n  contents: write\n" in text
    assert "cancel-in-progress: false" in text
    assert "if: github.ref == 'refs/heads/main'" in text
    scripts = [textwrap.dedent(block) for block in re.findall(r"^        run: \|\n((?:          .*\n|\n)+)", text, re.MULTILINE)]
    commands = "\n".join(scripts)
    assert "python scripts/collect_memory_prices.py" in commands
    assert "--check" in commands
    assert "[skip render]" in commands
    assert "for attempt in 1 2 3" in commands
    assert "git pull --rebase origin main" in commands
    assert "git push origin HEAD:main" in commands
    assert "--force" not in commands
    assert "secrets." not in text
    assert "/api/memory" not in commands
    import subprocess
    assert scripts
    for script in scripts:
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)
