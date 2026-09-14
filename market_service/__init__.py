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

install_patch(_legacy)
_legacy.__name__ = __name__
_legacy.__package__ = ""
sys.modules[__name__] = _legacy
