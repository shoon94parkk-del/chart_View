"""Compatibility shim that adds a realtime Korean-index provider.

The project historically keeps the implementation in ``market_service.py``.
Python prefers this package over the sibling module, so we load that file as the
actual module object, install the narrow KOSPI/KOSDAQ override, and then publish
the loaded module under the original ``market_service`` name. Existing tests and
callers therefore keep patching/using the same globals as before.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_legacy_path = Path(__file__).resolve().parent.parent / "market_service.py"
_spec = importlib.util.spec_from_file_location("_chartview_market_service_legacy", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load legacy market service: {_legacy_path}")

_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _legacy
_spec.loader.exec_module(_legacy)

from realtime_korea import install_patch
from snapshot_warmer import start_snapshot_warmer

install_patch(_legacy)
# Render-only daemon: keep shared Home/market snapshots hot every five minutes.
# The helper is a no-op in local development and CI because RENDER_EXTERNAL_URL
# is not present there.
start_snapshot_warmer()

_legacy.__name__ = __name__
_legacy.__package__ = ""
sys.modules[__name__] = _legacy
