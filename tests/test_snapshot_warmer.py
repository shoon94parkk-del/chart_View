import importlib


def test_snapshot_warmer_is_disabled_outside_render(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    mod = importlib.import_module("snapshot_warmer")
    mod._started = False
    assert mod.WARM_INTERVAL_SEC == 300
    assert mod.start_snapshot_warmer() is False
    assert mod._started is False


def test_snapshot_warmer_starts_only_once_on_render(monkeypatch):
    mod = importlib.import_module("snapshot_warmer")
    mod._started = False
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")

    started = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            started.append((target, args, name, daemon))

        def start(self):
            started.append("started")

    monkeypatch.setattr(mod.threading, "Thread", FakeThread)

    assert mod.start_snapshot_warmer() is True
    assert mod.start_snapshot_warmer() is False
    assert len([x for x in started if x == "started"]) == 1
    target, args, name, daemon = started[0]
    assert target is mod._worker
    assert args == ("https://example.onrender.com",)
    assert name == "chartview-snapshot-warmer"
    assert daemon is True
