from copy import deepcopy

import pytest

from scripts import generate_earnings_event_cache as collector


CHECKED = "2026-10-16T01:52:05Z"
APPLE = '''<rss><channel><lastBuildDate>Mon, 02 Nov 2026 14:00:00 -0500</lastBuildDate><item>
<title>11/2/2026 : FY 26 Fourth Quarter Results</title>
<description>&lt;p&gt;Apple’s conference call to discuss fourth quarter results and business updates is scheduled for Monday, November 2, 2026 at 2:00 p.m. PT / 5:00 p.m. ET.&lt;/p&gt;</description>
<pubDate>Tue, 06 Oct 2026 17:09:11 -0400</pubDate>
<link>https://investor.apple.com/event-details/2026/FY-26-Fourth-Quarter-Results/default.aspx</link>
</item></channel></rss>'''
SAMSUNG = '''<ul class="ir-event-list"><li><dl class="ir-event-list__detail"><dt>3Q26 Guidance Announcement</dt><dd>October 8, 2026</dd></dl></li>
<li><dl class="ir-event-list__detail"><dt>3Q26 Earnings Conference Call</dt><dd>October 29, 2026, 10:00 a.m. KST</dd></dl></li></ul>'''


def test_apple_uses_explicit_call_text_not_rss_channel_or_pubdate():
    rows = collector.parse_apple_events(APPLE, CHECKED)
    assert len(rows) == 1
    assert rows[0]["scheduledAt"] == "2026-11-02T22:00:00Z"
    assert rows[0]["source"]["publishedAt"] == "2026-10-06T21:09:11Z"
    assert rows[0]["source"]["checkedAt"] == CHECKED
    assert rows[0]["publishedAt"] is None


def test_apple_omits_time_if_only_fiscal_period_or_channel_date_is_available():
    xml = APPLE.replace(" at 2:00 p.m. PT / 5:00 p.m. ET.", ".")
    assert collector.parse_apple_events(xml, CHECKED) == []


def test_apple_disagreed_title_and_description_dates_are_rejected():
    assert collector.parse_apple_events(APPLE.replace("11/2/2026 :", "11/3/2026 :"), CHECKED) == []


def test_samsung_keeps_guidance_and_call_distinct():
    rows = collector.parse_samsung_events(SAMSUNG, CHECKED)
    assert len(rows) == 1
    assert rows[0]["scheduledAt"] == "2026-10-29T01:00:00Z"
    assert rows[0]["timezone"] == "Asia/Seoul"
    assert rows[0]["title"] == "3Q26 Earnings Conference Call"
    assert rows[0]["source"]["publishedAt"] is None


def test_unrecognized_source_structure_raises_instead_of_clearing_valid_cache():
    with pytest.raises(ValueError):
        collector.parse_samsung_events("<html>Unavailable</html>", CHECKED)


def test_refresh_failure_retains_original_success_time_and_call():
    row = collector.parse_apple_events(APPLE, CHECKED)[0]
    old = {"sources": {"AAPL": {"status": "ok", "checkedAt": CHECKED}}, "events": [deepcopy(row)]}
    def fetch(_url):
        raise TimeoutError("request credentials must not be copied into errors")
    updated = collector.build_cache(old, checked_at="2026-10-17T01:00:00Z", fetch=fetch)
    assert updated["events"] == [row]
    assert updated["sources"]["AAPL"]["checkedAt"] == CHECKED
    assert updated["sources"]["AAPL"]["attemptedAt"] == "2026-10-17T01:00:00Z"
    assert updated["sources"]["AAPL"]["errorCode"] == "TimeoutError"
    assert "credentials" not in str(updated)


def test_refresh_has_three_official_requests_and_no_yahoo_or_consensus_reads():
    calls = []
    def fetch(url):
        calls.append(url)
        if "apple.com" in url:
            return APPLE
        if "samsung.com" in url:
            return SAMSUNG
        return "<rss><channel></channel></rss>"
    updated = collector.build_cache({}, checked_at=CHECKED, fetch=fetch)
    assert len(calls) == 3
    assert all("yahoo" not in url for url in calls)
    assert len(updated["events"]) == 2
    assert updated["sources"]["NVDA"]["status"] == "ok"
    assert updated["sources"]["NVDA"]["checkedAt"] == CHECKED
    assert updated["sources"]["000660.KS"]["status"] == "not_collected"


def test_successful_refresh_does_not_accumulate_past_call_history():
    old_samsung = SAMSUNG.replace("October 29, 2026", "October 29, 2025")
    def fetch(url):
        if "apple.com" in url:
            return APPLE
        if "samsung.com" in url:
            return old_samsung
        return "<rss><channel></channel></rss>"
    updated = collector.build_cache({}, checked_at=CHECKED, fetch=fetch)
    assert [row["symbol"] for row in updated["events"]] == ["AAPL"]
