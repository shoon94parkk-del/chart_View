"""Reuse provider HTTP connections within a thread, retaining Requests defaults.

The caller still owns headers, timeouts, status checking and JSON parsing. This
module adds neither retries nor a response cache. Sessions retain environment
proxy/CA trust and are never shared between executor threads.
"""
from __future__ import annotations

import threading
from typing import Any

import requests

_state = threading.local()


def get(url: str, **kwargs: Any) -> requests.Response:
    session = getattr(_state, "session", None)
    if session is None:
        session = _state.session = requests.Session()
    return session.get(url, **kwargs)
