"""Provider-free reader for optional, independently precomputed release data."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CACHE_PATH = Path(__file__).resolve().parent / 'static' / 'data' / 'inflation_release_cache.json'


def load_inflation_release_cache(path: Path | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Read saved data only; a missing/broken optional cache must not affect macro."""
    unavailable = {
        'inflation': {'schemaVersion': 1, 'status': 'unavailable', 'series': []},
        'releaseCalendar': {'status': 'unavailable', 'checkedAt': None, 'events': []},
    }
    try:
        data = json.loads((path or CACHE_PATH).read_text(encoding='utf-8'))
        inflation, calendar = data['inflation'], data['releaseCalendar']
        if not isinstance(inflation, dict) or not isinstance(inflation.get('series'), list):
            return unavailable
        if not isinstance(calendar, dict) or not isinstance(calendar.get('events'), list):
            return unavailable
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable
    current = now or datetime.now(timezone.utc)
    upcoming = []
    for event in calendar['events']:
        if not isinstance(event, dict):
            continue
        try:
            if event.get('scheduledAt'):
                if not isinstance(event['scheduledAt'], str):
                    continue
                instant = datetime.fromisoformat(event['scheduledAt'].replace('Z', '+00:00'))
                if instant.tzinfo is None or instant < current:
                    continue
            elif date.fromisoformat(event['localDate']) < current.astimezone(ZoneInfo('America/New_York')).date():
                continue
        except (ValueError, KeyError, TypeError):
            continue
        upcoming.append(event)
    calendar['events'] = upcoming
    return {'inflation': inflation, 'releaseCalendar': calendar}
