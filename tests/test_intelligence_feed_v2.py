"""Offline regression tests: GET /api/intelligence/feed/v2.

Covers the task requirements:
- v1/v2 separation: v2 rejects v1 documents; routes do not collide.
- allowlist: forbidden private key names block publication; unknown
  extra keys are stripped, not passed through.
- unverified picks are refused: non-PASS audit_status, missing
  fact_pack_hash/audit_hash, empty picks, non-https evidence.
- ETag / If-None-Match behaviour.
- disabled by default (env unset) -> 503.
- stale snapshots are flagged, never disguised as current.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from intelligence_feed_v2_service import (
    etag_for,
    load_feed_v2,
    router,
    v2_projection,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
OLD = NOW - timedelta(hours=30)


def _pick(**overrides):
    pick = {
        "pick_id": "KR-20261019-005930",
        "market": "KR",
        "ticker": "005930",
        "verdict": "BUY",
        "decided_at": NOW.isoformat(),
        "decision_date": "2026-10-19",
        "thesis": "메모리 수요 회복 + HBM 공급 규율 유지 가설.",
        "evidence_urls": ["https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260813001713"],
        "falsifiers": [{"id": "F1", "metric": "D램 현물가 전월 대비 -10% 이상 하락"}],
        "fact_pack_hash": "sha256:FACTPACK",
        "audit_hash": "sha256:AUDITHASH",
        "audit_status": "PASS",
        "status": "유지",
        "source": "three_agent_audited",
    }
    pick.update(overrides)
    return pick


def _doc(picks=None, **overrides):
    doc = {
        "schema_version": 2,
        "kind": "market_research",
        "publication_status": "AUDITED_PICKS",
        "as_of": NOW.isoformat(),
        "generated_at": NOW.isoformat(),
        "run_key": "test-run-1",
        "coverage": "KR+US",
        "coverage_status": "COMPLETE",
        "quality_status": "COMPLETE",
        "failure_state": None,
        "picks": [_pick()] if picks is None else picks,
    }
    doc.update(overrides)
    return doc


def _v1_doc():
    # v1 contract shape (from PR #160): RESEARCH_ONLY, picks fixed to [].
    return {
        "schema_version": 1, "kind": "market_research",
        "publication_status": "RESEARCH_ONLY",
        "as_of": NOW.isoformat(),
        "coverage_status": "PARTIAL_COVERAGE",
        "quality_status": "COMPLETE",
        "candidates": [], "market_events": [],
        "picks": [], "pick_history": [],
    }


def _client_with_feed(doc) -> TestClient:
    tmp = TemporaryDirectory()
    path = Path(tmp.name) / "feed-v2.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    client._tmpdir = tmp  # keep alive for the test lifetime
    client._feed_path = str(path)
    return client


class FeedV2ProjectionTests(TestCase):
    def test_valid_document_projects_allowlisted(self):
        out = v2_projection(_doc())
        self.assertEqual(out["schema_version"], 2)
        self.assertEqual(out["publication_status"], "AUDITED_PICKS")
        self.assertEqual(out["picks"][0]["source"], "three_agent_audited")
        self.assertIn("as_of", out)
        self.assertIn("generated_at", out)

    def test_v1_document_rejected(self):
        # v1/v2 separation: a v1 RESEARCH_ONLY document is not a v2 document.
        with self.assertRaises(ValueError):
            v2_projection(_v1_doc())

    def test_source_is_stamped_not_trusted(self):
        out = v2_projection(_doc(picks=[_pick(source="forged-source")]))
        self.assertEqual(out["picks"][0]["source"], "three_agent_audited")

    def test_unknown_extra_keys_stripped(self):
        doc = _doc()
        doc["note"] = "예시 데이터"
        doc["example"] = True
        doc["picks"][0]["private_thesis"] = "secret notes"
        out = v2_projection(doc)
        self.assertNotIn("note", out)
        self.assertNotIn("example", out)
        self.assertNotIn("private_thesis", out["picks"][0])
        self.assertNotIn("secret notes", json.dumps(out))

    def test_forbidden_key_names_block_publication(self):
        for fragment in ("api_key", "apikey", "secret", "password", "token",
                         "account_id", "private_key", "db_path", "dsn"):
            with self.subTest(fragment=fragment):
                doc = _doc()
                doc["picks"][0][f"my_{fragment}"] = "x"
                with self.assertRaises(ValueError):
                    v2_projection(doc)
        # also at top level
        doc = _doc()
        doc["operator_token"] = "x"
        with self.assertRaises(ValueError):
            v2_projection(doc)

    def test_non_pass_audit_status_rejected(self):
        for status in ("FAIL", "PENDING", "pass", "", None):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    v2_projection(_doc(picks=[_pick(audit_status=status)]))

    def test_missing_hashes_rejected(self):
        pick = _pick()
        del pick["fact_pack_hash"]
        with self.assertRaises(ValueError):
            v2_projection(_doc(picks=[pick]))
        pick = _pick()
        del pick["audit_hash"]
        with self.assertRaises(ValueError):
            v2_projection(_doc(picks=[pick]))

    def test_empty_picks_rejected(self):
        with self.assertRaises(ValueError):
            v2_projection(_doc(picks=[]))

    def test_non_https_evidence_rejected(self):
        with self.assertRaises(ValueError):
            v2_projection(_doc(picks=[_pick(
                evidence_urls=["http://example.com/x"])]))

    def test_bad_ticker_rejected(self):
        with self.assertRaises(ValueError):
            v2_projection(_doc(picks=[_pick(ticker="bad ticker!")]))

    def test_long_thesis_rejected(self):
        with self.assertRaises(ValueError):
            v2_projection(_doc(picks=[_pick(thesis="x" * 201)]))

    def test_future_or_naive_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            v2_projection(_doc(as_of="2099-01-01T00:00:00+09:00"))
        with self.assertRaises(ValueError):
            v2_projection(_doc(generated_at="2026-10-19T16:00:00"))

    def test_failure_state_passthrough(self):
        failure = {"code": "PARTIAL", "message": "일부 커버리지",
                   "at": NOW.isoformat()}
        out = v2_projection(_doc(failure_state=failure))
        self.assertEqual(out["failure_state"]["code"], "PARTIAL")

    def test_etag_is_stable_and_quoted(self):
        out = v2_projection(_doc())
        tag = etag_for(out)
        self.assertEqual(tag, etag_for(out))
        self.assertTrue(tag.startswith('"') and tag.endswith('"'))
        self.assertEqual(len(tag), 34)  # 32 hex chars + quotes


class FeedV2RouteTests(TestCase):
    def test_route_path_does_not_collide_with_v1(self):
        paths = sorted({r.path for r in router.routes
                        if getattr(r, "path", None)})
        self.assertEqual(paths, ["/api/intelligence/feed/v2"])

    def test_disabled_by_default_503(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict(os.environ, {}, clear=True):
            resp = client.get("/api/intelligence/feed/v2")
        self.assertEqual(resp.status_code, 503)

    def test_relative_path_refused(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict(os.environ,
                        {"MARKET_INTELLIGENCE_FEED_V2_PATH": "relative.json"},
                        clear=True):
            resp = client.get("/api/intelligence/feed/v2")
        self.assertEqual(resp.status_code, 503)

    def test_serves_valid_feed_with_etag(self):
        client = _client_with_feed(_doc())
        self.addCleanup(client._tmpdir.cleanup)
        with patch.dict(os.environ,
                        {"MARKET_INTELLIGENCE_FEED_V2_PATH": client._feed_path},
                        clear=True):
            resp = client.get("/api/intelligence/feed/v2")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["publication_status"], "AUDITED_PICKS")
        self.assertEqual(len(body["picks"]), 1)
        self.assertIn("ETag", resp.headers)
        self.assertEqual(resp.headers["Cache-Control"], "public, max-age=60")
        self.assertNotIn("X-Feed-Stale", resp.headers)

    def test_if_none_match_returns_304(self):
        client = _client_with_feed(_doc())
        self.addCleanup(client._tmpdir.cleanup)
        with patch.dict(os.environ,
                        {"MARKET_INTELLIGENCE_FEED_V2_PATH": client._feed_path},
                        clear=True):
            first = client.get("/api/intelligence/feed/v2")
            etag = first.headers["ETag"]
            resp = client.get("/api/intelligence/feed/v2",
                              headers={"If-None-Match": etag})
        self.assertEqual(resp.status_code, 304)

    def test_invalid_feed_file_503(self):
        client = _client_with_feed(_doc(picks=[]))  # fails closed
        self.addCleanup(client._tmpdir.cleanup)
        with patch.dict(os.environ,
                        {"MARKET_INTELLIGENCE_FEED_V2_PATH": client._feed_path},
                        clear=True):
            resp = client.get("/api/intelligence/feed/v2")
        self.assertEqual(resp.status_code, 503)

    def test_stale_feed_is_flagged_not_disguised(self):
        client = _client_with_feed(_doc(generated_at=OLD.isoformat()))
        self.addCleanup(client._tmpdir.cleanup)
        with patch.dict(os.environ,
                        {"MARKET_INTELLIGENCE_FEED_V2_PATH": client._feed_path},
                        clear=True):
            resp = client.get("/api/intelligence/feed/v2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Feed-Stale"), "true")
        # the snapshot's own timestamps stay visible — not rewritten
        self.assertEqual(resp.json()["generated_at"], OLD.isoformat())

    def test_oversize_file_rejected(self):
        doc = _doc()
        doc["picks"][0]["thesis"] = "x" * (512 * 1024)
        client = _client_with_feed(doc)
        self.addCleanup(client._tmpdir.cleanup)
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ,
                            {"MARKET_INTELLIGENCE_FEED_V2_PATH":
                             client._feed_path}):
                with self.assertRaises(ValueError):
                    load_feed_v2()

    def test_v1_env_var_does_not_enable_v2(self):
        # v1 and v2 are configured independently.
        tmp = TemporaryDirectory()
        path = Path(tmp.name) / "feed.json"
        path.write_text(json.dumps(_v1_doc()), encoding="utf-8")
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict(os.environ,
                        {"MARKET_INTELLIGENCE_FEED_PATH": str(path)},
                        clear=True):
            resp = client.get("/api/intelligence/feed/v2")
        self.assertEqual(resp.status_code, 503)
