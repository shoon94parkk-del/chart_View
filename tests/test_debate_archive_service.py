import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from debate_archive_service import public_archive, load_archive, public_shadow_status

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
    def extended(self):
        doc = fixture()
        row = doc['debates'][0]
        row.update(summary='수요와 밸류에이션을 함께 재점검', updated_at=doc['generated_at'])
        phase = row['phases'][0]
        row['phases'] = [dict(phase, role=role, stage='phase1') for role in ('mer', 'nonggu', 'meng')]
        row['phases'] += [dict(phase, stage=stage) for stage in ('attack', 'rebuttal', 'final')]
        return doc
    def test_new_public_summary_and_timestamp_are_projected(self):
        doc = self.extended()
        row = public_archive(doc)['debates'][0]
        self.assertEqual(row['summary'], doc['debates'][0]['summary'])
        self.assertEqual(row['updated_at'], doc['generated_at'])
    def test_extended_completed_requires_three_independent_analyses_and_final_rounds(self):
        for stage, role in [('phase1', 'mer'), ('attack', 'meng'), ('rebuttal', 'meng'), ('final', 'meng')]:
            doc = self.extended()
            doc['debates'][0]['phases'] = [p for p in doc['debates'][0]['phases'] if not (p['stage'] == stage and p['role'] == role)]
            with self.subTest(stage=stage, role=role), self.assertRaises(ValueError): public_archive(doc)
    def test_invalid_extension_does_not_silently_become_legacy(self):
        for change in ({'summary':''}, {'summary':'a'*601}, {'updated_at':'2026-10-21'}, {'updated_at':None}):
            doc = self.extended(); doc['debates'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): public_archive(doc)
    def test_all_metadata_and_unknown_strings_are_scanned_for_private_data(self):
        for field in ('company', 'topic', 'summary', 'extra'):
            doc = self.extended(); doc['debates'][0][field] = '본인 보유 수량 300주'
            with self.subTest(field=field), self.assertRaises(ValueError): public_archive(doc)
        for field in ('holdings','positions','portfolio','quantity','avg_cost','cost_basis','account','user_id','watchlist'):
            doc = self.extended(); doc['debates'][0][field] = 3
            with self.subTest(field=field), self.assertRaises(ValueError): public_archive(doc)
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
    def test_refuses_private_prose_even_with_approval(self):
        for sample in ("연락처 010-1234-5678", "email: person@example.com",
                       "현재 보유 1.12억원", "계정 ghp_abcdefghijklmnopqrstuvwxyz0123",
                       "password=example-secret", "api_key=AIza-example", "계좌번호 123-456-789",
                       "my portfolio has shares"):
            doc = fixture()
            doc["debates"][0]["phases"][0]["text"] = sample
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    public_archive(doc)
    def test_shadow_record_source_allowed_and_traversal_still_rejected(self):
        v = fixture()
        v["debates"][0]["phases"][0]["source_path"] = "records/shadow/2026-10-20-smoke/272210-mer-phase1.md"
        self.assertEqual(public_archive(v)["debates"][0]["phases"][0]["source_path"], v["debates"][0]["phases"][0]["source_path"])
        v["debates"][0]["phases"][0]["source_path"] = "records/shadow/../../private.md"
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

class TestShadowStatus(unittest.TestCase):
    def sample(self):
        stamp = datetime.now(timezone.utc).isoformat()
        return {"schema_version":1, "kind":"shadow_status",
                "publication_status":"EXPLICITLY_APPROVED",
                "generated_at":stamp,"state":"RUNNING",
                "period_started_at":stamp,"last_execution_at":stamp,
                "runs_total":2,"screenings_total":1,"debates_total":1,
                "audits_approved":0,"audits_blocked":1,"failures_total":0,
                "smoke_runs_total":1,"smoke_audits_approved":1}

    def test_real_status_counts(self):
        result=public_shadow_status(self.sample())
        self.assertEqual(result["state"],"RUNNING")

    def test_running_needs_real_execution(self):
        value=self.sample()
        value["last_execution_at"]=None
        with self.assertRaises(ValueError):public_shadow_status(value)

    def test_sensitive_extra_rejected(self):
        value=self.sample()
        value["password"]="private"
        with self.assertRaises(ValueError):public_shadow_status(value)

    def test_archived_smoke_remains_separate(self):
        value=self.sample()
        value["state"]="NOT_STARTED"
        value["last_execution_at"]=None
        value["period_started_at"]=None
        value["runs_total"]=0
        value["screenings_total"]=0
        value["debates_total"]=0
        value["audits_blocked"]=0
        self.assertEqual(public_shadow_status(value)["smoke_runs_total"],1)
        value["smoke_audits_approved"]=2
        with self.assertRaises(ValueError):public_shadow_status(value)

    def test_audits_cannot_exceed_debates(self):
        value=self.sample()
        value["audits_approved"]=5
        with self.assertRaises(ValueError):public_shadow_status(value)
