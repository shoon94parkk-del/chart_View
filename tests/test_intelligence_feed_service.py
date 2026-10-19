"""Offline tests: never expose private fields, publish unverified picks or files."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from intelligence_feed_service import load_feed, public_projection


def fixture():
    from datetime import datetime, timezone
    return {
        "schema_version": 1, "kind": "market_research",
        "publication_status": "RESEARCH_ONLY",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "coverage_status": "PARTIAL_COVERAGE",
        "quality_status": "COMPLETE",
        "candidates": [{
            "ticker": "000660", "market": "KR", "stage": "DISCOVERED",
            "score": 65.0, "buy_eligible": False, "private_thesis": "secret",
        }],
        "market_events": [{
            "id": "MARKET:vix:test:2026-10-19", "severity": "WARNING",
            "action": "REVIEW_ONLY", "requires_review": True,
            "private_account": "secret",
        }],
        "picks": [], "pick_history": [], "private_portfolio": "secret",
    }


class IntelligenceFeedTests(TestCase):
    def test_projection_strips_sensitive_and_unexpected_keys(self):
        out = public_projection(fixture())
        self.assertEqual(out["candidates"][0]["score"], 65.0)
        self.assertNotIn("secret", json.dumps(out))
        self.assertEqual(out["picks"], [])
        self.assertEqual(out["market_events"][0]["action"], "REVIEW_ONLY")

    def test_unverified_buy_fails_closed(self):
        doc = fixture()
        doc["picks"] = [{"ticker": "000660", "verdict": "BUY"}]
        with self.assertRaises(ValueError):
            public_projection(doc)
        doc = fixture()
        doc["candidates"][0]["buy_eligible"] = True
        with self.assertRaises(ValueError):
            public_projection(doc)

    def test_reject_future_or_naive_timestamp(self):
        doc = fixture()
        doc["as_of"] = "2099-01-01T00:00:00+09:00"
        with self.assertRaises(ValueError):
            public_projection(doc)
        doc["as_of"] = "2026-10-19T16:00:00"
        with self.assertRaises(ValueError):
            public_projection(doc)

    def test_file_explicit_optin_only(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                load_feed()
        with TemporaryDirectory() as path:
            file = Path(path) / "feed.json"
            file.write_text(json.dumps(fixture()), encoding="utf-8")
            with patch.dict(os.environ, {"MARKET_INTELLIGENCE_FEED_PATH": str(file)}):
                self.assertEqual(load_feed()["publication_status"], "RESEARCH_ONLY")
