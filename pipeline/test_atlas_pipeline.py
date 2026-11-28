"""Critical gate tests. All positive reviews/receipts below are FIXTURES, not live QA."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from atlas_pipeline import CHECKS, IDEA_ROLES, GateError, Ledger, file_digest, validate_manifest


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="_test_", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "ledger.sqlite3"
        self.ledger = Ledger(self.db_path, allow_fixture_evidence=True)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def create(self, idea="fixture-1", *, brief=None, formats=None, max_attempts=3):
        return self.ledger.create(idea_id=idea, brand="fixture-brand", brief=brief or {"title": "Fixture only"},
                                  required_formats=formats or {"tool": "web"}, source_sha="a" * 40,
                                  builder_id="fixture-builder", max_attempts=max_attempts, now=1)

    def approve_idea(self, job, *, same_reviewer=False, suffix="v1"):
        current = self.ledger.job(job)
        for role in IDEA_ROLES:
            self.ledger.review_idea(job, {
                "role": role, "reviewer_id": "fixture-same" if same_reviewer else f"fixture-{role}",
                "decision": "APPROVE", "source_sha": current["source_sha"], "brief_hash": current["brief_hash"],
                "reason": "Synthetic unit-test approval; no actual review performed",
                "evidence_ref": f"fixture:{role}:{suffix}", "evidence_mode": "fixture"})

    def artifact(self, job, lease, *, format_name="tool", kind="web", mime="text/html", now=10):
        current = self.ledger.job(job)
        path = self.root / f"{job[:12]}-{format_name}.html"
        path.write_text("<!doctype html><title>UNIT TEST FIXTURE</title><p>Not client content</p>")
        sha = file_digest(path)
        artifact = {"format": format_name, "kind": kind, "path": str(path), "mime_type": mime,
                    "source_sha": current["source_sha"], "brief_hash": current["brief_hash"],
                    "sha256": sha, "byte_length": path.stat().st_size,
                    "durable_receipt": {"provider": "unit-test-fixture", "object_id": "fixture-object",
                        "retrieval_uri": "fixture://not-a-real-upload", "durable": True,
                        "readback_sha256": sha, "byte_length": path.stat().st_size, "verified_at": 10,
                        "evidence_ref": "fixture:simulated-readback", "evidence_mode": "fixture"}}
        self.ledger.record_artifact(job, lease, artifact, now=now)
        return artifact

    def approve_artifact(self, job, artifact, *, suffix="v1"):
        self.ledger.review_artifact(job, artifact["format"], {
            "reviewer_id": "fixture-independent-editor", "decision": "PASS", "evidence_mode": "fixture",
            "artifact_hash": artifact["sha256"], "source_sha": artifact["source_sha"], "brief_hash": artifact["brief_hash"],
            "checks": {name: {"passed": True, "evidence_ref": f"fixture:{name}:{suffix}"}
                       for name in CHECKS[artifact["kind"]]}})

    def ready(self, idea="fixture-ready", *, at=100):
        job = self.create(idea)
        lease = self.ledger.claim(job, "fixture-worker", now=at - 5)
        self.approve_idea(job)
        artifact = self.artifact(job, lease, now=at - 4)
        self.approve_artifact(job, artifact)
        result = self.ledger.mark_ready(job, lease, now=at)
        self.assertTrue(result["ready"], result)
        return job, artifact

    def test_idempotent_intake_and_lease_fencing_with_bounded_retries(self):
        job = self.create()
        self.assertEqual(job, self.create())
        second = Ledger(self.db_path, allow_fixture_evidence=True)
        try:
            old = self.ledger.claim(job, "worker-a", lease_seconds=5, now=10)
            self.assertIsNone(second.claim(job, "worker-b", now=12))
            new = second.claim(job, "worker-b", now=16)
            self.assertGreater(new["fence"], old["fence"])
            with self.assertRaises(GateError):
                self.ledger.fail(job, old, "stale write", now=17)
            self.assertEqual("RETRY", second.fail(job, new, "429 fixture", retryable=True, now=17))
            self.assertIsNone(self.ledger.claim(job, "worker-c", now=136))
            final = self.ledger.claim(job, "worker-c", now=137)
            self.assertEqual("EXHAUSTED", self.ledger.fail(job, final, "still failing", retryable=True, now=138))
            self.assertIsNone(second.claim(job, "worker-d", now=10000))
            self.assertEqual(3, self.ledger.job(job)["attempts"])
        finally:
            second.close()

    def test_independent_review_board_and_fixture_evidence_is_not_live(self):
        job = self.create()
        current = self.ledger.job(job)
        with self.assertRaises(GateError):
            self.ledger.review_idea(job, {"role": "relevance", "reviewer_id": "fixture-builder",
                "brief_hash": current["brief_hash"], "source_sha": current["source_sha"], "decision": "APPROVE"})
        self.approve_idea(job, same_reviewer=True)
        self.assertIn("Idea board requires three distinct reviewers", self.ledger.gate_errors(job))
        self.approve_idea(job)
        strict_errors = validate_manifest(self.ledger.manifest(job))
        self.assertTrue(any("genuine review evidence missing" in error for error in strict_errors))
        self.assertIn("Invalid source commit hash", validate_manifest({"schema_version": 1}))

    def test_source_change_invalidates_qa_and_old_worker(self):
        job = self.create()
        lease = self.ledger.claim(job, "worker", now=10)
        self.approve_idea(job)
        artifact = self.artifact(job, lease)
        self.approve_artifact(job, artifact)
        self.assertEqual([], self.ledger.gate_errors(job))
        self.ledger.revise_source(job, "b" * 40, "a" * 40)
        errors = self.ledger.gate_errors(job)
        self.assertIn("tool: stale artifact source/brief", errors)
        self.assertIn("tool: passing QA missing", errors)
        with self.assertRaises(GateError):
            self.ledger.mark_ready(job, lease, now=12)
        with self.assertRaises(GateError):
            self.approve_artifact(job, artifact)

    def test_corruption_and_durable_receipt_mismatch_block_ready(self):
        job = self.create()
        lease = self.ledger.claim(job, "worker", now=10)
        self.approve_idea(job)
        artifact = self.artifact(job, lease)
        self.approve_artifact(job, artifact)
        artifact["durable_receipt"]["readback_sha256"] = "0" * 64
        self.ledger.record_artifact(job, lease, artifact, now=11)
        self.assertIn("tool: durable read-back checksum/size mismatch", self.ledger.gate_errors(job))
        artifact["durable_receipt"]["readback_sha256"] = artifact["sha256"]
        self.ledger.record_artifact(job, lease, artifact, now=12)
        Path(artifact["path"]).write_text("Changed after approval")
        result = self.ledger.mark_ready(job, lease, now=13)
        self.assertFalse(result["ready"])
        self.assertIn("tool: artifact missing or bytes changed after QA", result["errors"])
        self.assertEqual("BLOCKED", self.ledger.job(job)["state"])

    def test_required_formats_and_uninspected_motion_audio_cannot_pass(self):
        job = self.create(formats={"tool": "web", "vertical": "video"})
        lease = self.ledger.claim(job, "worker", now=10)
        self.approve_idea(job)
        tool = self.artifact(job, lease)
        self.approve_artifact(job, tool)
        self.assertIn("vertical: exactly one current artifact required", self.ledger.gate_errors(job))
        self.artifact(job, lease, format_name="vertical", kind="video", mime="text/plain")
        result = self.ledger.mark_ready(job, lease, now=11)
        self.assertFalse(result["ready"])
        for message in ("a storyboard is not rendered video", "motion_review evidence missing", "audio_review evidence missing"):
            self.assertTrue(any(message in error for error in result["errors"]), result)

    def test_revised_brief_supersedes_ready_work_and_cached_roundup(self):
        at = int(datetime(2026, 11, 25, 12, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp())
        old, artifact = self.ready("same-idea", at=at)
        intent = self.ledger.prepare_outbox(old, destination="fixture-platform", account_id="fixture-account",
                    operation="native_draft", payload={"text": "fixture", "media_sha256": artifact["sha256"]})
        edition = self.ledger.roundup("fixture-brand", "2026-11-23", now=at + 1)
        self.assertEqual(1, len(edition["items"]))
        new = self.create("same-idea", brief={"title": "Revised fixture"})
        self.assertNotEqual(new, old)
        self.assertEqual("SUPERSEDED", self.ledger.job(old)["state"])
        self.assertIn("Idea revision has been superseded", self.ledger.gate_errors(old))
        self.assertIsNone(self.ledger.start_outbox(intent, "sender", now=at + 2))
        self.assertEqual("BLOCKED", self.ledger.outbox(intent)["state"])
        self.assertEqual("BLOCKED_STALE", self.ledger.roundup("fixture-brand", "2026-11-23", now=at + 3)["status"])
        with self.assertRaises(GateError):
            self.create("same-idea")

    def test_outbox_dedup_reapproval_and_unknown_result_reconciliation(self):
        job, artifact = self.ready(at=100)
        args = {"destination": "fixture-platform", "account_id": "fixture-account", "operation": "native_draft",
                "payload": {"text": "fixture", "media_sha256": artifact["sha256"]}}
        first = self.ledger.prepare_outbox(job, **args)
        self.approve_idea(job, suffix="changed-evidence-not-content")
        self.ledger.resume(job)
        lease = self.ledger.claim(job, "worker-2", now=101)
        self.assertTrue(self.ledger.mark_ready(job, lease, now=102)["ready"])
        self.assertEqual(first, self.ledger.prepare_outbox(job, **args))
        self.assertEqual(args["payload"], json.loads(self.ledger.outbox(first)["payload_json"]))
        token = self.ledger.start_outbox(first, "sender", lease_seconds=5, now=103)
        self.assertIsNone(self.ledger.start_outbox(first, "second-sender", now=104))
        self.assertIsNone(self.ledger.start_outbox(first, "recovery", now=109))
        self.assertEqual("UNKNOWN", self.ledger.outbox(first)["state"])
        with self.assertRaises(GateError):
            self.ledger.finish_outbox(first, token, external_id="late", evidence_ref="fixture:late", now=110)
        self.ledger.reconcile_outbox(first, evidence_ref="fixture:lookup", found_external_id="fixture-existing-draft")
        self.assertIsNone(self.ledger.start_outbox(first, "sender", now=111))
        self.assertEqual(1, self.ledger.outbox(first)["attempts"])
        self.assertEqual("fixture-existing-draft", self.ledger.outbox(first)["external_id"])

    def test_weekly_snapshot_ready_only_dst_boundary_and_null_metrics(self):
        zone = ZoneInfo("America/Los_Angeles")
        at = int(datetime(2026, 10, 28, 12, tzinfo=zone).timestamp())
        ready, _ = self.ready("ready-item", at=at)
        self.create("unfinished-item")
        edition = self.ledger.roundup("fixture-brand", "2026-10-26", now=at + 1)
        self.assertEqual([ready], [item["job_id"] for item in edition["items"]])
        self.assertEqual(169 * 3600, edition["end_utc_exclusive"] - edition["start_utc"])
        self.assertTrue(all(value is None for value in edition["items"][0]["metrics"].values()))
        self.assertEqual("NOT_VERIFIED", edition["items"][0]["publication_status"])
        self.ready("late-item", at=at + 2)
        self.assertEqual(edition, self.ledger.roundup("fixture-brand", "2026-10-26", now=at + 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
