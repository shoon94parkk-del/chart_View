"""Refresh three official public schedule pages, never analyst/quote providers.

Three requests, 12 seconds each, no retries. Failed source checks preserve the
last successful observations, including their original check timestamps.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Callable
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from earnings_event_service import CACHE_PATH, ISSUERS, SCHEMA_VERSION, parse_timestamp, validate_event

SOURCES = {
    "AAPL": "https://investor.apple.com/rss/Event.aspx?LanguageId=1",
    "005930.KS": "https://www.samsung.com/global/ir/ir-events-presentations/events/",
    "NVDA": "https://investor.nvidia.com/rss/Event.aspx?LanguageId=1",
}


def _row(symbol: str, title: str, scheduled: datetime, zone: str, content: str, checked: str, published: str | None = None) -> dict:
    issuer = ISSUERS[symbol]
    stamp = scheduled.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "id": f"{symbol}:earnings_call:{stamp}", "symbol": symbol, "name": issuer["name"],
        "title": title, "eventType": "earnings_call", "timingRole": "conference_call",
        "scheduledAt": stamp, "timezone": zone, "publishedAt": None,
        "source": {"name": issuer["sourceName"], "url": issuer["url"], "evidenceUrl": SOURCES[symbol],
                   "publishedAt": published, "checkedAt": checked, "contentSha256": hashlib.sha256(content.encode("utf-8")).hexdigest()},
    }


def parse_apple_events(content: str, checked_at: str) -> list[dict]:
    root = ET.fromstring(content)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("unrecognized Apple event feed")
    rows = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        description = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)
        description = re.sub(r"\s+", " ", description)
        if "conference call" not in description.lower() or "quarter" not in title.lower():
            continue
        date_match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", description)
        title_date = re.match(r"(\d{1,2}/\d{1,2}/\d{4})\s*:", title)
        time_match = re.search(r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s+ET\b", description, re.I)
        if not all((date_match, title_date, time_match)):
            continue
        date = datetime.strptime(date_match.group(1), "%B %d, %Y")
        if date.date() != datetime.strptime(title_date.group(1), "%m/%d/%Y").date():
            continue
        hour, minute, ampm = int(time_match.group(1)), int(time_match.group(2)), time_match.group(3).lower()
        if not (1 <= hour <= 12 and 0 <= minute < 60):
            continue
        hour = hour % 12 + (12 if ampm == "p" else 0)
        scheduled = date.replace(hour=hour, minute=minute, tzinfo=ZoneInfo("America/New_York"))
        published = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if item.findtext("pubDate") else None
        rows.append(_row("AAPL", title.split(":", 1)[-1].strip() + " conference call", scheduled, "America/New_York", content, checked_at, published))
    return rows


def parse_samsung_events(content: str, checked_at: str) -> list[dict]:
    soup = BeautifulSoup(content, "html.parser")
    details = soup.select("dl.ir-event-list__detail")
    if not details:
        raise ValueError("unrecognized Samsung event page")
    rows = []
    for item in details:
        title = item.find("dt")
        date = item.find("dd")
        if not title or not date or "Earnings Conference Call" not in title.get_text(" ", strip=True):
            continue
        date_text = date.get_text(" ", strip=True)
        match = re.fullmatch(r"([A-Z][a-z]+ \d{1,2}, \d{4}),\s*(\d{1,2}):(\d{2})\s*([ap])\.m\.\s+KST", date_text, re.I)
        if not match:
            continue
        date = datetime.strptime(match.group(1), "%B %d, %Y")
        hour, minute = int(match.group(2)), int(match.group(3))
        if not (1 <= hour <= 12 and 0 <= minute < 60):
            continue
        hour = hour % 12 + (12 if match.group(4).lower() == "p" else 0)
        scheduled = date.replace(hour=hour, minute=minute, tzinfo=ZoneInfo("Asia/Seoul"))
        rows.append(_row("005930.KS", title.get_text(" ", strip=True), scheduled, "Asia/Seoul", content, checked_at))
    return rows


def _nvidia_events(content: str, _checked_at: str) -> list[dict]:
    root = ET.fromstring(content)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("unrecognized NVIDIA event feed")
    # Current official feed is empty. A new format needs verified timing parsing;
    # do not replace it with Yahoo's conflicting call/earnings timestamps.
    if root.findall("./channel/item"):
        raise ValueError("NVIDIA event timing requires verification")
    return []


PARSERS = {"AAPL": parse_apple_events, "005930.KS": parse_samsung_events, "NVDA": _nvidia_events}


def build_cache(old: dict, *, checked_at: str, fetch: Callable[[str], str]) -> dict:
    events = old.get("events") if isinstance(old.get("events"), list) else []
    old_sources = old.get("sources") if isinstance(old.get("sources"), dict) else {}
    sources, next_events = {}, []
    for symbol, url in SOURCES.items():
        try:
            content = fetch(url)
            rows = PARSERS[symbol](content, checked_at)
            for row in rows:
                validate_event(row)
            next_events.extend(row for row in rows if parse_timestamp(row["scheduledAt"]) > parse_timestamp(checked_at))
            sources[symbol] = {"status": "ok", "checkedAt": checked_at, "attemptedAt": checked_at, "sourceUrl": ISSUERS[symbol]["url"], "evidenceUrl": url}
        except Exception as exc:
            previous = old_sources.get(symbol) or {}
            sources[symbol] = {"status": "error", "checkedAt": previous.get("checkedAt"), "attemptedAt": checked_at, "errorCode": type(exc).__name__, "sourceUrl": ISSUERS[symbol]["url"], "evidenceUrl": url}
            next_events.extend(row for row in events if isinstance(row, dict) and row.get("symbol") == symbol)
    sources["000660.KS"] = {"status": "not_collected", "checkedAt": None, "attemptedAt": None, "reason": "official_schedule_not_collected"}
    return {"schemaVersion": SCHEMA_VERSION, "generatedAt": checked_at, "sources": sources, "events": next_events}


def fetch_official_page(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": "ChartView official-schedule-check/1.0"}, timeout=12, allow_redirects=False)
    if response.is_redirect:
        raise ValueError("schedule source redirected; reverify canonical source")
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("schedule response exceeds size bound")
    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=CACHE_PATH)
    args = parser.parse_args()
    try:
        old = json.loads(args.output.read_text(encoding="utf-8"))
        if not isinstance(old, dict):
            old = {}
    except (OSError, ValueError):
        old = {}
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cache = build_cache(old, checked_at=stamp, fetch=fetch_official_page)
    successes = sum(row["status"] == "ok" for row in cache["sources"].values())
    if not successes:
        raise SystemExit("all official schedule checks failed; existing cache preserved")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(f"official schedule sources checked={successes}/{len(SOURCES)}; call rows={len(cache['events'])}; requests<=3; timeout=12s; retries=0")


if __name__ == "__main__":
    main()
