import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from debate_archive_service import public_archive, load_archive

def fixture():
    now = datetime.now(timezone.utc).isoformat()
    return {"schema_version": 1, "kind": "debate_archive", "publication_status": "EXPLICITLY_APPROVED",
        "generated_at": now,
        "debates": [{"id": "apr_20261013", "ticker": "278470", "company": "에이피알",
            "date": "2026-10-13", "topic": "기존 연구", "status": "COMPLETED",
            "verdict": "WAIT", "audit_verified": False,
            "phases": [{"stage": "attack", "role": "meng", "title": "공격", "text": "수요 데이터 확인 필요",
                        "source_path": "records/debates/20261013-picks/apr-phase2.md"}]}]}

class TestDebateArchive(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(public_archive(fixture())["debates"][0]["verdict"], "WAIT")
    def test_must_explicitly_approve(self):
        v = fixture(); v["publication_status"] = "DRAFT"
        with self.assertRaises(ValueError): public_archive(v)
    def test_cannot_mark_archive_as_audited(self):
        v = fixture(); v["debates"][0]["audit_verified"] = True
        with self.assertRaises(ValueError): public_archive(v)
    def test_no_sensitive_fields_even_nested(self):
        v = fixture(); v["debates"][0]["phases"][0]["api_key"] = "bad"
        with self.assertRaises(ValueError): public_archive(v)
    def test_no_traversal(self):
        v = fixture(); v["debates"][0]["phases"][0]["source_path"] = "records/debates/../../.env.md"
        with self.assertRaises(ValueError): public_archive(v)
    def test_duplicate_ids_fail(self):
        v = fixture(); v["debates"] *= 2
        with self.assertRaises(ValueError): public_archive(v)
    def test_rebuild_drops_nonprivate_extra(self):
        v = fixture(); v["debates"][0]["untrusted_extension"] = "x"
        self.assertNotIn("untrusted_extension", public_archive(v)["debates"][0])
    def test_default_503_gate(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError): load_archive()
    def test_explicit_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "approved.json")
            with open(path, "w", encoding="utf-8") as f: json.dump(fixture(), f)
            with patch.dict(os.environ, {"INTEL_DEBATE_FEED_PATH": path}):
                doc, etag = load_archive()
                self.assertEqual(len(doc["debates"]), 1)
                self.assertTrue(etag.startswith('"'))
if __name__ == "__main__": unittest.main()
