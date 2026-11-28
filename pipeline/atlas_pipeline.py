#!/usr/bin/env python3
"""Local Atlas release gates and durable-host ledger. No network or publication code.

This validates recorded evidence; it does not create or authenticate that evidence.
The caller must capture genuine reviews, storage read-backs and platform responses.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from zoneinfo import ZoneInfo


SCHEMA_VERSION = 1
IDEA_ROLES = ("relevance", "originality", "accuracy")
CHECKS = {
    "web": ("ui_interaction", "changed_input", "invalid_input", "export_verified"),
    "video": ("full_decode", "motion_review", "audio_review", "caption_review", "claims_review"),
    "image": ("visual_review", "claims_review"),
    "carousel": ("visual_review", "slide_sequence", "claims_review"),
    "text": ("editorial_review", "claims_review"),
}


class GateError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def timestamp(value=None):
    return int(time.time() if value is None else value)


def require(value, message):
    if not value:
        raise GateError(message)


def validate_source_sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value),
            "source_sha must be a full lowercase Git commit hash")
    return value


class Ledger:
    def __init__(self, path=":memory:", *, allow_fixture_evidence=False):
        self.allow_fixture_evidence = allow_fixture_evidence
        self.db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, idea_id TEXT NOT NULL, brand TEXT NOT NULL,
          brief_json TEXT NOT NULL, brief_hash TEXT NOT NULL, formats_json TEXT NOT NULL,
          source_sha TEXT NOT NULL, builder_id TEXT NOT NULL, pipeline_version TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'PENDING', created_at INTEGER NOT NULL, ready_at INTEGER,
          manifest_hash TEXT, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
          owner TEXT, lease_until INTEGER, fence INTEGER NOT NULL DEFAULT 0,
          next_attempt_at INTEGER NOT NULL DEFAULT 0, last_error TEXT);
        CREATE TABLE IF NOT EXISTS idea_reviews (
          job_id TEXT NOT NULL REFERENCES jobs(id), role TEXT NOT NULL, reviewer_id TEXT NOT NULL,
          brief_hash TEXT NOT NULL, source_sha TEXT NOT NULL, review_json TEXT NOT NULL,
          PRIMARY KEY(job_id, role, brief_hash, source_sha));
        CREATE TABLE IF NOT EXISTS current_ideas (
          idea_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id));
        CREATE TABLE IF NOT EXISTS artifacts (
          job_id TEXT NOT NULL REFERENCES jobs(id), format TEXT NOT NULL, artifact_json TEXT NOT NULL,
          PRIMARY KEY(job_id, format));
        CREATE TABLE IF NOT EXISTS qa_reviews (
          job_id TEXT NOT NULL REFERENCES jobs(id), format TEXT NOT NULL, artifact_hash TEXT NOT NULL,
          source_sha TEXT NOT NULL, brief_hash TEXT NOT NULL, review_json TEXT NOT NULL,
          PRIMARY KEY(job_id, format, artifact_hash, source_sha, brief_hash));
        CREATE TABLE IF NOT EXISTS outbox (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), destination TEXT NOT NULL,
          account_id TEXT NOT NULL, operation TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
          manifest_hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
          attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
          owner TEXT, lease_until INTEGER, fence INTEGER NOT NULL DEFAULT 0,
          external_id TEXT, evidence_ref TEXT);
        CREATE TABLE IF NOT EXISTS editions (
          id TEXT PRIMARY KEY, payload_json TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def job(self, job_id):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        require(row is not None, "Unknown job")
        return dict(row)

    def create(self, *, idea_id, brand, brief, required_formats, source_sha: str,
               builder_id, pipeline_version="1", max_attempts=3, now=None):
        require(bool(idea_id and brand and builder_id and brief), "Idea, brand, builder and brief are required")
        require(isinstance(required_formats, dict) and required_formats, "Required format map is empty")
        require(all(isinstance(k, str) and k and v in CHECKS for k, v in required_formats.items()),
                "Every required format must name a supported kind")
        require(1 <= max_attempts <= 10, "max_attempts must be 1..10")
        source_sha = validate_source_sha(source_sha)
        brief_hash = digest({"brief": brief, "required_formats": required_formats})
        job_id = digest({"idea_id": idea_id, "brief_hash": brief_hash, "pipeline_version": pipeline_version})
        with self.transaction():
            existing = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if existing:
                require(existing["brand"] == brand and existing["builder_id"] == builder_id,
                        "Idempotent intake conflicts with existing brand/builder")
                require(existing["source_sha"] == source_sha,
                        "Source changed: use explicit revise-source, not duplicate intake")
                current = self.db.execute("SELECT job_id FROM current_ideas WHERE idea_id=?", (idea_id,)).fetchone()
                require(current and current[0] == job_id, "This intake revision has been superseded")
                return job_id
            self.db.execute("""UPDATE jobs SET state='SUPERSEDED',ready_at=NULL,manifest_hash=NULL,
              owner=NULL,lease_until=NULL,fence=fence+1 WHERE idea_id=?""", (idea_id,))
            self.db.execute("""UPDATE outbox SET state='BLOCKED' WHERE state='PENDING'
              AND job_id IN (SELECT id FROM jobs WHERE idea_id=?)""", (idea_id,))
            self.db.execute("""INSERT INTO jobs
              (id,idea_id,brand,brief_json,brief_hash,formats_json,source_sha,builder_id,
               pipeline_version,created_at,max_attempts) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
              (job_id, idea_id, brand, canonical(brief), brief_hash, canonical(required_formats),
               source_sha, builder_id, pipeline_version, timestamp(now), max_attempts))
            self.db.execute("INSERT OR REPLACE INTO current_ideas VALUES (?,?)", (idea_id, job_id))
        return job_id

    def claim(self, job_id, owner, *, lease_seconds=300, now=None):
        now = timestamp(now)
        require(bool(owner), "Owner is required")
        require(1 <= lease_seconds <= 3600, "Lease must be 1..3600 seconds")
        with self.transaction():
            job = self.job(job_id)
            eligible = job["state"] in ("PENDING", "RETRY") and job["next_attempt_at"] <= now
            expired = job["state"] == "RUNNING" and job["lease_until"] <= now
            if not (eligible or expired):
                return None
            if job["attempts"] >= job["max_attempts"]:
                self.db.execute("UPDATE jobs SET state='EXHAUSTED',owner=NULL,lease_until=NULL WHERE id=?", (job_id,))
                return None
            fence = job["fence"] + 1
            self.db.execute("""UPDATE jobs SET state='RUNNING',owner=?,lease_until=?,fence=?,
              attempts=attempts+1 WHERE id=?""", (owner, now + lease_seconds, fence, job_id))
            return {"owner": owner, "fence": fence, "lease_until": now + lease_seconds}

    def _check_lease(self, job, lease, now):
        require(job["state"] == "RUNNING" and lease is not None and
                job["owner"] == lease.get("owner") and job["fence"] == lease.get("fence") and
                job["lease_until"] > now, "Missing, expired or superseded worker lease")

    def heartbeat(self, job_id, lease, *, lease_seconds=300, now=None):
        now = timestamp(now)
        require(1 <= lease_seconds <= 3600, "Lease must be 1..3600 seconds")
        with self.transaction():
            self._check_lease(self.job(job_id), lease, now)
            self.db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (now + lease_seconds, job_id))
        return {**lease, "lease_until": now + lease_seconds}

    def fail(self, job_id, lease, error, *, retryable=False, now=None):
        now = timestamp(now)
        with self.transaction():
            job = self.job(job_id)
            self._check_lease(job, lease, now)
            state = "BLOCKED"
            if retryable:
                state = "RETRY" if job["attempts"] < job["max_attempts"] else "EXHAUSTED"
            due = now + min(60 * 2 ** (job["attempts"] - 1), 3600)
            self.db.execute("""UPDATE jobs SET state=?,owner=NULL,lease_until=NULL,
              next_attempt_at=?,last_error=? WHERE id=?""", (state, due, str(error), job_id))
        return state

    def resume(self, job_id):
        with self.transaction():
            job = self.job(job_id)
            require(job["state"] == "BLOCKED", "Only explicitly repaired BLOCKED jobs can resume")
            require(job["attempts"] < job["max_attempts"], "Retry budget exhausted; create an intentional new revision")
            self.db.execute("UPDATE jobs SET state='PENDING',next_attempt_at=0 WHERE id=?", (job_id,))

    def revise_source(self, job_id, new_source_sha, expected_source_sha):
        new_source_sha = validate_source_sha(new_source_sha)
        with self.transaction():
            job = self.job(job_id)
            require(job["state"] != "SUPERSEDED", "Cannot revise a superseded brief")
            require(job["source_sha"] == expected_source_sha, "Source revision conflict")
            if new_source_sha == expected_source_sha:
                return
            self.db.execute("""UPDATE jobs SET source_sha=?,state='PENDING',ready_at=NULL,
              manifest_hash=NULL,owner=NULL,lease_until=NULL,fence=fence+1,attempts=0,
              next_attempt_at=0,last_error='Source changed; reviews and artifacts must be refreshed' WHERE id=?""",
              (new_source_sha, job_id))

    def review_idea(self, job_id, review):
        with self.transaction():
            job = self.job(job_id)
            require(review.get("role") in IDEA_ROLES, "Unknown idea reviewer role")
            require(review.get("reviewer_id") and review["reviewer_id"] != job["builder_id"],
                    "Builder cannot approve own idea")
            require(review.get("brief_hash") == job["brief_hash"] and review.get("source_sha") == job["source_sha"],
                    "Idea review does not match current brief/source")
            require(review.get("decision") in ("APPROVE", "REVISE", "REJECT"), "Invalid review decision")
            require(review.get("evidence_ref") and review.get("reason"), "Review needs evidence and a reason")
            self.db.execute("INSERT OR REPLACE INTO idea_reviews VALUES (?,?,?,?,?,?)",
              (job_id, review["role"], review["reviewer_id"], job["brief_hash"], job["source_sha"], canonical(review)))
            self._invalidate_ready(job_id)

    def _invalidate_ready(self, job_id):
        self.db.execute("""UPDATE jobs SET state=CASE WHEN state='READY' THEN 'BLOCKED' ELSE state END,
          ready_at=NULL,manifest_hash=NULL WHERE id=?""", (job_id,))

    def record_artifact(self, job_id, lease, artifact, *, now=None):
        artifact = dict(artifact)
        with self.transaction():
            job = self.job(job_id)
            self._check_lease(job, lease, timestamp(now))
            formats = json.loads(job["formats_json"])
            require(artifact.get("format") in formats, "Artifact format is not required by this job")
            require(artifact.get("kind") == formats[artifact["format"]], "Artifact kind disagrees with format profile")
            require(artifact.get("source_sha") == job["source_sha"] and artifact.get("brief_hash") == job["brief_hash"],
                    "Artifact does not match current source/brief")
            path = Path(artifact["path"]).resolve()
            require(path.is_file(), "Artifact file does not exist")
            actual = file_digest(path)
            require(artifact.get("sha256") == actual, "Artifact SHA-256 does not match bytes")
            require(artifact.get("byte_length") == path.stat().st_size and path.stat().st_size > 0,
                    "Artifact byte length is wrong or empty")
            require(bool(artifact.get("mime_type")), "Artifact MIME type missing")
            artifact["path"] = str(path)
            self.db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?)",
                            (job_id, artifact["format"], canonical(artifact)))
            self._invalidate_ready(job_id)

    def review_artifact(self, job_id, format_name, review):
        with self.transaction():
            job = self.job(job_id)
            row = self.db.execute("SELECT artifact_json FROM artifacts WHERE job_id=? AND format=?",
                                  (job_id, format_name)).fetchone()
            require(row is not None, "Record artifact before its QA")
            artifact = json.loads(row[0])
            require(review.get("reviewer_id") and review["reviewer_id"] != job["builder_id"],
                    "Builder cannot approve own artifact")
            require(review.get("artifact_hash") == artifact["sha256"] and
                    review.get("source_sha") == job["source_sha"] == artifact["source_sha"] and
                    review.get("brief_hash") == job["brief_hash"] == artifact["brief_hash"],
                    "QA does not match current artifact/source/brief")
            require(review.get("decision") in ("PASS", "FAIL"), "QA decision must be PASS or FAIL")
            self.db.execute("INSERT OR REPLACE INTO qa_reviews VALUES (?,?,?,?,?,?)",
              (job_id, format_name, artifact["sha256"], job["source_sha"], job["brief_hash"], canonical(review)))
            self._invalidate_ready(job_id)

    def manifest(self, job_id):
        job = self.job(job_id)
        ideas = [json.loads(row[0]) for row in self.db.execute(
            "SELECT review_json FROM idea_reviews WHERE job_id=? AND brief_hash=? AND source_sha=? ORDER BY role",
            (job_id, job["brief_hash"], job["source_sha"]))]
        artifacts = []
        for row in self.db.execute("SELECT artifact_json FROM artifacts WHERE job_id=? ORDER BY format", (job_id,)):
            artifact = json.loads(row[0])
            qa = self.db.execute("""SELECT review_json FROM qa_reviews WHERE job_id=? AND format=?
              AND artifact_hash=? AND source_sha=? AND brief_hash=?""",
              (job_id, artifact["format"], artifact["sha256"], job["source_sha"], job["brief_hash"])).fetchone()
            artifacts.append({**artifact, "qa": json.loads(qa[0]) if qa else None})
        return {"schema_version": SCHEMA_VERSION, "job_id": job_id, "idea_id": job["idea_id"],
                "is_current_revision": self.db.execute("SELECT job_id FROM current_ideas WHERE idea_id=?", (job["idea_id"],)).fetchone()[0] == job_id,
                "brand": job["brand"], "brief_hash": job["brief_hash"], "source_sha": job["source_sha"],
                "builder_id": job["builder_id"], "pipeline_version": job["pipeline_version"],
                "required_formats": json.loads(job["formats_json"]), "idea_reviews": ideas, "artifacts": artifacts}

    def gate_errors(self, job_id, *, verify_files=True):
        return validate_manifest(self.manifest(job_id), verify_files=verify_files,
                                 allow_fixture_evidence=self.allow_fixture_evidence)

    def mark_ready(self, job_id, lease, *, now=None):
        now = timestamp(now)
        with self.transaction():
            self._check_lease(self.job(job_id), lease, now)
            errors = self.gate_errors(job_id)
            if errors:
                self.db.execute("""UPDATE jobs SET state='BLOCKED',owner=NULL,lease_until=NULL,
                  ready_at=NULL,manifest_hash=NULL,last_error=? WHERE id=?""", (canonical(errors), job_id))
                return {"ready": False, "errors": errors}
            manifest_hash = digest(self.manifest(job_id))
            self.db.execute("""UPDATE jobs SET state='READY',ready_at=?,manifest_hash=?,owner=NULL,
              lease_until=NULL,last_error=NULL WHERE id=?""", (now, manifest_hash, job_id))
            return {"ready": True, "errors": [], "manifest_hash": manifest_hash}

    def prepare_outbox(self, job_id, *, destination, account_id, operation, payload, max_attempts=3):
        require(operation == "native_draft", "Only native_draft intents are supported; publication is not implemented")
        require(destination and account_id and payload, "Destination, account and exact payload are required")
        require(1 <= max_attempts <= 10, "Outbox max_attempts must be 1..10")
        with self.transaction():
            job = self.job(job_id)
            require(job["state"] == "READY" and not self.gate_errors(job_id), "Only validated READY work may create draft intents")
            manifest_hash = digest(self.manifest(job_id))
            require(manifest_hash == job["manifest_hash"], "Ready manifest changed")
            payload_hash = digest(payload)
            # Review metadata is authorization evidence, not a second draft identity.
            key = digest([job["idea_id"], destination, account_id, operation, payload_hash])
            self.db.execute("""INSERT OR IGNORE INTO outbox
              (id,job_id,destination,account_id,operation,payload_hash,payload_json,manifest_hash,max_attempts)
              VALUES (?,?,?,?,?,?,?,?,?)""",
              (key, job_id, destination, account_id, operation, payload_hash, canonical(payload), manifest_hash, max_attempts))
            # Fresh approval may refresh an unsent intent. Never reset a known or uncertain send.
            self.db.execute("""UPDATE outbox SET job_id=?,manifest_hash=?,state='PENDING'
              WHERE id=? AND attempts=0 AND state IN ('PENDING','BLOCKED')""", (job_id, manifest_hash, key))
            return key

    def outbox(self, key):
        row = self.db.execute("SELECT * FROM outbox WHERE id=?", (key,)).fetchone()
        require(row is not None, "Unknown outbox intent")
        return dict(row)

    def start_outbox(self, key, owner, *, lease_seconds=300, now=None):
        now = timestamp(now)
        require(owner and 1 <= lease_seconds <= 3600, "Valid owner and lease required")
        with self.transaction():
            row = self.outbox(key)
            if row["state"] == "SENDING" and row["lease_until"] <= now:
                self.db.execute("UPDATE outbox SET state='UNKNOWN',owner=NULL,lease_until=NULL WHERE id=?", (key,))
                return None
            if row["state"] != "PENDING":
                return None
            require(digest(json.loads(row["payload_json"])) == row["payload_hash"], "Outbox payload corrupted")
            job = self.job(row["job_id"])
            if job["state"] != "READY" or self.gate_errors(job["id"]) or digest(self.manifest(job["id"])) != row["manifest_hash"]:
                self.db.execute("UPDATE outbox SET state='BLOCKED' WHERE id=?", (key,))
                return None
            if row["attempts"] >= row["max_attempts"]:
                self.db.execute("UPDATE outbox SET state='EXHAUSTED' WHERE id=?", (key,))
                return None
            token = {"owner": owner, "fence": row["fence"] + 1, "lease_until": now + lease_seconds}
            self.db.execute("""UPDATE outbox SET state='SENDING',owner=?,fence=?,lease_until=?,
              attempts=attempts+1 WHERE id=?""", (owner, token["fence"], token["lease_until"], key))
            return token

    def finish_outbox(self, key, token, *, external_id=None, uncertain=False, evidence_ref, now=None):
        require(evidence_ref, "External result evidence is required")
        require(bool(external_id) != bool(uncertain), "Record either a known external ID or an uncertain outcome")
        with self.transaction():
            row = self.outbox(key)
            require(row["state"] == "SENDING" and row["owner"] == token.get("owner") and
                    row["fence"] == token.get("fence") and row["lease_until"] > timestamp(now),
                    "Stale outbox lease; reconcile instead")
            self.db.execute("""UPDATE outbox SET state=?,external_id=?,evidence_ref=?,owner=NULL,
              lease_until=NULL WHERE id=?""", ("UNKNOWN" if uncertain else "SUCCEEDED", external_id, evidence_ref, key))

    def reconcile_outbox(self, key, *, evidence_ref, found_external_id=None, confirmed_absent=False):
        require(evidence_ref and (bool(found_external_id) != bool(confirmed_absent)),
                "Reconciliation requires evidence of one existing result or confirmed absence")
        with self.transaction():
            row = self.outbox(key)
            require(row["state"] == "UNKNOWN", "Only UNKNOWN outcomes require reconciliation")
            state = "SUCCEEDED" if found_external_id else ("PENDING" if row["attempts"] < row["max_attempts"] else "EXHAUSTED")
            self.db.execute("UPDATE outbox SET state=?,external_id=?,evidence_ref=? WHERE id=?",
                            (state, found_external_id, evidence_ref, key))

    def roundup(self, brand, week_start, *, timezone="America/Los_Angeles", now=None):
        start_date = date.fromisoformat(week_start)
        require(start_date.weekday() == 0, "week_start must be a Monday in the chosen timezone")
        zone = ZoneInfo(timezone)
        start = datetime.combine(start_date, dt_time(), zone)
        end = datetime.combine(start_date + timedelta(days=7), dt_time(), zone)
        start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
        cutoff = min(timestamp(now), end_ts)
        require(cutoff >= start_ts, "Cannot create an edition before its interval begins")
        key = digest([brand, week_start, timezone, "edition-v1"])
        with self.transaction():
            existing = self.db.execute("SELECT payload_json FROM editions WHERE id=?", (key,)).fetchone()
            if existing:
                edition = json.loads(existing[0])
                stale = [item["job_id"] for item in edition["items"]
                         if self.job(item["job_id"])["state"] != "READY"
                         or self.gate_errors(item["job_id"], verify_files=False)
                         or digest(self.manifest(item["job_id"])) != item["manifest_hash"]]
                if stale:
                    return {**edition, "status": "BLOCKED_STALE", "blocked_job_ids": stale}
                return edition
            items = []
            rows = self.db.execute("""SELECT * FROM jobs WHERE brand=? AND state='READY'
              AND ready_at>=? AND ready_at<? AND ready_at<=? ORDER BY ready_at,id""",
              (brand, start_ts, end_ts, cutoff)).fetchall()
            for row in rows:
                manifest = self.manifest(row["id"])
                if self.gate_errors(row["id"], verify_files=False) or digest(manifest) != row["manifest_hash"]:
                    continue
                items.append({"job_id": row["id"], "idea_id": row["idea_id"], "manifest_hash": row["manifest_hash"],
                              "artifacts": [{k: a[k] for k in ("format", "sha256", "durable_receipt")} for a in manifest["artifacts"]],
                              "publication_status": "NOT_VERIFIED", "platform_post_ids": [],
                              "metrics": {k: None for k in ("views", "impressions", "likes", "comments", "shares", "watch_time_seconds")}})
            edition = {"edition_id": key, "brand": brand, "week_start": week_start, "timezone": timezone,
                       "start_utc": start_ts, "end_utc_exclusive": end_ts, "cutoff_utc": cutoff,
                       "status": "DRAFT_PACKAGE", "selection": "READY_CONTENT_NOT_PUBLICATION_OR_PERFORMANCE", "items": items}
            self.db.execute("INSERT INTO editions VALUES (?,?)", (key, canonical(edition)))
            return edition


def validate_manifest(manifest, *, verify_files=True, allow_fixture_evidence=False):
    """Validate declarations and exact bytes; never infer that human/media QA happened."""
    if not isinstance(manifest, dict):
        return ["Manifest must be a JSON object"]
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    def live(record):
        return record.get("evidence_mode") == "live" or (allow_fixture_evidence and record.get("evidence_mode") == "fixture")
    check(manifest.get("schema_version") == SCHEMA_VERSION, "Unsupported manifest schema")
    for key in ("job_id", "idea_id", "brand", "builder_id", "pipeline_version"):
        check(isinstance(manifest.get(key), str) and bool(manifest[key]), f"Manifest {key} missing")
    check(bool(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(manifest.get("source_sha", "")))), "Invalid source commit hash")
    check(bool(re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("brief_hash", "")))), "Invalid brief hash")
    check(manifest.get("is_current_revision") is True, "Idea revision has been superseded")
    formats = manifest.get("required_formats", {})
    check(isinstance(formats, dict) and bool(formats), "Required formats missing")
    if not isinstance(formats, dict):
        return errors
    check(all(kind in CHECKS for kind in formats.values()), "Unsupported format kind")
    reviewers = []
    for role in IDEA_ROLES:
        matching = [r for r in manifest.get("idea_reviews", []) if r.get("role") == role]
        review = matching[0] if len(matching) == 1 else {}
        check(review.get("decision") == "APPROVE", f"Idea {role}: current approval missing")
        check(live(review), f"Idea {role}: genuine review evidence missing")
        check(review.get("brief_hash") == manifest.get("brief_hash") and review.get("source_sha") == manifest.get("source_sha"),
              f"Idea {role}: stale review")
        reviewer = review.get("reviewer_id")
        check(bool(reviewer) and reviewer != manifest.get("builder_id"), f"Idea {role}: reviewer is not independent")
        check(bool(review.get("reason") and review.get("evidence_ref")), f"Idea {role}: evidence/reason missing")
        reviewers.append(reviewer)
    check(len(set(reviewers)) == len(IDEA_ROLES), "Idea board requires three distinct reviewers")
    artifacts = manifest.get("artifacts", [])
    for name, kind in formats.items():
        matches = [a for a in artifacts if a.get("format") == name]
        if len(matches) != 1:
            errors.append(f"{name}: exactly one current artifact required")
            continue
        artifact = matches[0]
        check(artifact.get("kind") == kind, f"{name}: kind mismatch")
        check(artifact.get("source_sha") == manifest.get("source_sha") and artifact.get("brief_hash") == manifest.get("brief_hash"),
              f"{name}: stale artifact source/brief")
        sha = artifact.get("sha256", "")
        check(isinstance(sha, str) and bool(re.fullmatch(r"[0-9a-f]{64}", sha)), f"{name}: invalid SHA-256")
        check(isinstance(artifact.get("byte_length"), int) and artifact["byte_length"] > 0, f"{name}: invalid byte length")
        check(bool(artifact.get("mime_type")), f"{name}: MIME type missing")
        if kind == "video":
            check(str(artifact.get("mime_type", "")).startswith("video/"), f"{name}: a storyboard is not rendered video")
            check(all(isinstance(artifact.get(k), (int, float)) and artifact[k] > 0
                      for k in ("width", "height", "duration_seconds", "frame_rate")), f"{name}: video probe properties missing")
        if verify_files:
            try:
                path = Path(artifact["path"])
                check(path.is_file() and file_digest(path) == sha and path.stat().st_size == artifact.get("byte_length"),
                      f"{name}: artifact missing or bytes changed after QA")
            except (OSError, KeyError, TypeError):
                errors.append(f"{name}: artifact cannot be read")
        qa = artifact.get("qa") or {}
        check(qa.get("decision") == "PASS", f"{name}: passing QA missing")
        check(live(qa), f"{name}: genuine independent QA missing")
        check(bool(qa.get("reviewer_id")) and qa.get("reviewer_id") != manifest.get("builder_id"), f"{name}: QA reviewer is not independent")
        check(qa.get("artifact_hash") == sha and qa.get("source_sha") == manifest.get("source_sha") and
              qa.get("brief_hash") == manifest.get("brief_hash"), f"{name}: stale QA hashes")
        checks = qa.get("checks", {})
        for expected in CHECKS.get(kind, ()):
            observed = checks.get(expected, {}) if isinstance(checks, dict) else {}
            check(isinstance(observed, dict) and observed.get("passed") is True and bool(observed.get("evidence_ref")),
                  f"{name}: {expected} evidence missing or failed")
        receipt = artifact.get("durable_receipt") or {}
        check(live(receipt), f"{name}: genuine durable storage receipt missing")
        check(receipt.get("durable") is True and all(receipt.get(k) for k in ("provider", "object_id", "retrieval_uri", "verified_at", "evidence_ref")),
              f"{name}: durable object identity/read-back evidence missing")
        check(receipt.get("readback_sha256") == sha and receipt.get("byte_length") == artifact.get("byte_length"),
              f"{name}: durable read-back checksum/size mismatch")
    return errors


def load_json(path):
    return json.loads(Path(path).read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="atlas.sqlite3", help="Durable host path; defaults to current directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    create = commands.add_parser("create")
    create.add_argument("--input", required=True)
    for name in ("status", "manifest", "claim", "gate", "resume", "record", "review-idea", "review-artifact", "fail"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--job", required=True)
        if name == "claim":
            cmd.add_argument("--owner", required=True)
        if name in ("record", "review-idea", "review-artifact"):
            cmd.add_argument("--input", required=True)
        if name in ("record", "fail"):
            cmd.add_argument("--lease", required=True, help="JSON file returned by claim")
        if name == "gate":
            cmd.add_argument("--lease", help="If supplied, attempt READY; otherwise inspect only")
        if name == "review-artifact":
            cmd.add_argument("--format", required=True)
        if name == "fail":
            cmd.add_argument("--error", required=True)
            cmd.add_argument("--retryable", action="store_true")
    roundup = commands.add_parser("roundup")
    roundup.add_argument("--brand", required=True)
    roundup.add_argument("--week-start", required=True)
    roundup.add_argument("--timezone", default="America/Los_Angeles")
    validate = commands.add_parser("validate-manifest")
    validate.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    ledger = None
    try:
        if args.command == "validate-manifest":
            errors = validate_manifest(load_json(args.input))
            print(json.dumps({"ready": not errors, "errors": errors}, indent=2))
            return 2 if errors else 0
        ledger = Ledger(args.db)
        result = {"initialized": True, "schema_version": SCHEMA_VERSION}
        if args.command == "create":
            result = {"job_id": ledger.create(**load_json(args.input))}
        elif args.command == "status":
            result = ledger.job(args.job)
        elif args.command == "manifest":
            result = ledger.manifest(args.job)
        elif args.command == "claim":
            result = ledger.claim(args.job, args.owner)
        elif args.command == "gate":
            result = ledger.mark_ready(args.job, load_json(args.lease)) if args.lease else {"errors": ledger.gate_errors(args.job)}
            if not args.lease:
                result["ready"] = not result["errors"]
        elif args.command == "resume":
            ledger.resume(args.job)
            result = ledger.job(args.job)
        elif args.command == "record":
            ledger.record_artifact(args.job, load_json(args.lease), load_json(args.input))
            result = {"recorded": True}
        elif args.command == "review-idea":
            ledger.review_idea(args.job, load_json(args.input))
            result = {"recorded": True}
        elif args.command == "review-artifact":
            ledger.review_artifact(args.job, args.format, load_json(args.input))
            result = {"recorded": True}
        elif args.command == "fail":
            result = {"state": ledger.fail(args.job, load_json(args.lease), args.error, retryable=args.retryable)}
        elif args.command == "roundup":
            result = ledger.roundup(args.brand, args.week_start, timezone=args.timezone)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if isinstance(result, dict) and result.get("ready") is False else 0
    except (GateError, OSError, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        print(json.dumps({"error": str(error)}, indent=2), file=sys.stderr)
        return 2
    finally:
        if ledger:
            ledger.close()


if __name__ == "__main__":
    raise SystemExit(main())
