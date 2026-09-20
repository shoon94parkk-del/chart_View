"""Provider-aware market response contract shared by tests and live smoke."""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

REQUIRED = ("^KS11", "^KQ11", "^GSPC", "^IXIC", "^TNX", "^VIX", "CL=F", "KRW=X")
KOREA_SOURCES = {"Naver Finance KRX/Koscom", "Naver Finance realtime polling", "Yahoo Chart 5m"}


def validate_market_snapshot(data, now=None):
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    assert data.get("basis") == "previous_close", "unexpected price basis"
    assert data.get("date") == now.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat(), "snapshot collection date is not current"
    rows = {row.get("ticker"): row for row in data.get("results", [])}
    for ticker in REQUIRED:
        assert ticker in rows, f"missing quote: {ticker}"
        row = rows[ticker]
        allowed = KOREA_SOURCES if ticker in ("^KS11", "^KQ11") else {"Yahoo Chart 5m"}
        assert row.get("source") in allowed, f"unapproved source: {ticker} / {row.get('source')}"
        for field in ("price", "change"):
            value = row.get(field)
            assert isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"invalid {field}: {ticker}"
        assert row["price"] > 0, f"non-positive quote: {ticker}"
        stamp = datetime.fromisoformat(str(row.get("asOf", "")).replace("Z", "+00:00"))
        assert stamp.tzinfo is not None, f"quote timezone missing: {ticker}"
        assert (stamp - now).total_seconds() <= 300, f"future quote: {ticker}"
        assert isinstance(row.get("stale"), bool), f"freshness status missing: {ticker}"
        # Weekends/holidays legitimately retain the last session. Do not require
        # the quote itself to have today's date; require the explicit state.
        if ticker in ("^KS11", "^KQ11", "^GSPC", "^IXIC", "KRW=X"):
            assert abs(row["change"]) < 15, f"implausible daily change: {ticker}"
    return rows
