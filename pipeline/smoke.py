#!/usr/bin/env python3
"""Deterministic local diagnostic: success means the release gate REFUSES READY."""
import argparse
import json
from pathlib import Path
import sqlite3

from atlas_pipeline import IDEA_ROLES, Ledger, file_digest


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    tool = output / "diagnostic_tool.html"
    tool.write_text('''<!doctype html><meta charset="utf-8"><title>Pipeline diagnostic</title>
<h1>Pipeline diagnostic — not client content</h1>
<p>This tiny fixture has not passed browser or editorial review.</p>
<label>Example input <input id="amount" type="number" value="3"></label>
<button onclick="document.getElementById('result').textContent=Number(document.getElementById('amount').value)*2">Double</button>
<output id="result"></output>''', encoding="utf-8")
    storyboard = output / "diagnostic_storyboard.txt"
    storyboard.write_text("PIPELINE DIAGNOSTIC ONLY\nA storyboard is not a rendered film. No motion/audio inspection occurred.\n")
    ledger = Ledger()  # Strict mode. Fixture evidence never authorizes READY.
    inputs = {"idea_id": "diagnostic:local-only", "brand": "diagnostic", "brief": {"title": "Diagnostic only"},
              "required_formats": {"tool": "web", "vertical_video": "video"}, "source_sha": "a" * 40,
              "builder_id": "fixture-builder", "now": 100}
    job = ledger.create(**inputs)
    assert ledger.create(**inputs) == job
    lease = ledger.claim(job, "fixture-worker", now=101)
    current = ledger.job(job)
    for role in IDEA_ROLES:
        ledger.review_idea(job, {"role": role, "reviewer_id": f"fixture-{role}", "decision": "APPROVE",
            "brief_hash": current["brief_hash"], "source_sha": current["source_sha"], "evidence_mode": "fixture",
            "reason": "Synthetic record exercises gate rejection; no real review occurred", "evidence_ref": f"fixture:{role}"})
    for name, kind, path, mime in (("tool", "web", tool, "text/html"), ("vertical_video", "video", storyboard, "text/plain")):
        ledger.record_artifact(job, lease, {"format": name, "kind": kind, "path": str(path), "mime_type": mime,
            "sha256": file_digest(path), "byte_length": path.stat().st_size,
            "source_sha": current["source_sha"], "brief_hash": current["brief_hash"]}, now=102)
    result = ledger.mark_ready(job, lease, now=103)
    assert result["ready"] is False and ledger.job(job)["state"] == "BLOCKED"
    report = {"diagnostic_passed": True, "expected_release_gate": "BLOCKED", "actual_state": ledger.job(job)["state"],
              "production_ready": False, "connected_end_to_end_tested": False, "source_commit_verified": False,
              "real_motion_audio_ui_qa_performed": False, "durable_upload_performed": False,
              "platform_draft_created": False, "scheduler_execution_tested": False,
              "checks_exercised": ["SQLite job ledger", "idempotent intake", "local-file hashing", "refusal of unsupported READY"],
              "job_id": job, "gate_result": result}
    (output / "smoke_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "diagnostic_manifest.json").write_text(json.dumps(ledger.manifest(job), indent=2, sort_keys=True) + "\n")
    # This named diagnostic database is replaced on repeat runs. It is not production state.
    destination = sqlite3.connect(output / "diagnostic.sqlite3")
    ledger.db.backup(destination)
    destination.close()
    ledger.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(Path(__file__).parent / "_smoke"))
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, sort_keys=True))
