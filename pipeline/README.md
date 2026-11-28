# Atlas local release gates

This is runnable Python standard-library code for the local control layer: job identity, a SQLite ledger, evidence validation, leases, a draft-operation outbox, and weekly selection. It contains **no network connectors, uploads, scheduler, publication calls, or content-generation service**.

The included smoke diagnostic deliberately ends **BLOCKED**. No actual browser, motion, audio, independent editorial, durable storage, platform draft, or background scheduler leg has passed by running it.

## Run the verified checks

Python 3.10+ with timezone data is required; the implementation was tested with Python 3.12.14. From the parent directory containing `pipeline/`:

```bash
python3 -B -m unittest discover -s pipeline -p 'test_*.py' -v
python3 -B pipeline/smoke.py --output pipeline/_smoke
python3 -B pipeline/atlas_pipeline.py validate-manifest --input pipeline/_smoke/diagnostic_manifest.json
```

The first command passes eight logic tests. The second exits 0 **because it successfully demonstrates refusal of READY**. Its report says `production_ready: false`. The third exits **2**, correctly rejecting the diagnostic manifest.

`smoke.py` replaces only its named diagnostic outputs in the selected output directory on rerun. The diagnostic SQLite database is not production state. Generated files and SQLite files are excluded by `.gitignore`.

## What is enforced

- Intake identity uses idea identity, a canonical brief/required-format hash, and pipeline version. A duplicate intake returns the same job. A new brief atomically supersedes prior jobs for that idea; old READY states cannot continue authorizing work.
- Three distinct idea reviewers cover relevance, originality, and accuracy. The builder cannot approve their own idea or artifacts. Every idea decision references the exact brief and source hashes.
- Each required format must have a current artifact. Artifacts are registered against actual local bytes, byte length, source commit, and brief hash.
- QA is bound to the exact artifact, source, and brief. Required observations include UI interaction for tools and actual motion/audio inspection for videos. A storyboard does not qualify as a rendered video.
- READY requires a declared durable storage receipt with provider/object identity, read-back checksum and size, timestamp, and evidence reference. The local gate does not perform that upload or read-back.
- Fixture evidence is rejected in normal operation. Unit tests explicitly opt into fixtures; the CLI and smoke diagnostic do not expose that opt-in.
- Claims are transactional, time limited, and fenced. A recovered job increments the fencing token so an old worker cannot finalize. Attempts are bounded; retryable failures wait on exponential backoff. Failed content gates become BLOCKED and need an explicit repair/resume.
- Draft outbox entries retain exact canonical payloads and hashes. Identity depends on idea, destination, account, operation, and payload-not incidental review metadata. A changed review does not create a second logical draft for the same payload. An expired send becomes UNKNOWN and cannot retry until the remote outcome is reconciled.
- Weekly editions select only eligible READY items, use timezone-aware local week boundaries, preserve an immutable selection, and return `BLOCKED_STALE` if a selected item's current approval is later revoked. Publication status is unverified and missing metrics are `null`, never fabricated zeros.

## Trust boundary

This engine validates evidence records and local file integrity. **It cannot prove that a person/agent actually watched a film, that a reviewer identity is genuine, that a Git commit exists remotely, or that an object is durably stored.** The connector/controller must collect real evidence before supplying it. Writing `evidence_mode: "live"` manually does not establish those facts.

The controller must construct platform payloads from approved assets/copy, include exact media/content hashes in the payload, verify the destination account and native capability, and revalidate eligibility immediately before the remote call. The outbox does not itself create a draft. No public-publishing operation is implemented.

Use this local ledger with one trusted integration boundary. It is not a multi-user authentication or authorization service. Store credentials outside manifests, reviews, and payload logs.

## File and format contracts

Required formats are a map from meaningful rendition names to one of five supported kinds. Every declared rendition is required; this engine does not silently waive missing formats.

```json
{
  "interactive_tool": "web",
  "vertical_short": "video",
  "landscape_roundup": "video",
  "linkedin_document": "carousel",
  "companion_infographic": "image",
  "platform_copy": "text"
}
```

Video artifacts require positive probe fields: `width`, `height`, `duration_seconds`, and `frame_rate`, plus a video MIME type. The controller still needs profile-specific limits and actual FFmpeg/ffprobe evidence. The engine does not infer codec, caption quality, or editorial quality from filename/extensions.

Each artifact JSON contains:

```text
format, kind, path, mime_type, sha256, byte_length,
source_sha, brief_hash,
width, height, duration_seconds, frame_rate (video),
durable_receipt:
  provider, object_id, retrieval_uri, durable=true,
  readback_sha256, byte_length, verified_at, evidence_ref,
  evidence_mode=live
```

Each idea review contains `role`, `reviewer_id`, `decision` (`APPROVE`, `REVISE`, or `REJECT`), `brief_hash`, `source_sha`, `reason`, `evidence_ref`, and `evidence_mode`.

Each QA review contains `reviewer_id`, `decision` (`PASS` or `FAIL`), `artifact_hash`, `source_sha`, `brief_hash`, `evidence_mode`, and `checks`. Each required check is an object with `passed: true` and a real `evidence_ref`. See `CHECKS` in the source for the exact required observations by kind.

The manifest has no hash of itself. READY records its canonical SHA-256 in the ledger. A manifest references the artifact and review evidence used to authorize that state.

## CLI and Python integration

Initialize a production ledger only at a deliberately chosen durable-host location:

```bash
python3 -B pipeline/atlas_pipeline.py --db /chosen/durable/path/atlas.sqlite3 init
python3 -B pipeline/atlas_pipeline.py --db /chosen/durable/path/atlas.sqlite3 create --input intake.json
```

`intake.json` supplies `idea_id`, `brand`, `brief`, `required_formats`, a real full lowercase `source_sha`, `builder_id`, optional `pipeline_version`, and optional `max_attempts` (default 3).

Normal progression is:

1. `create --input intake.json`; retain the returned job ID.
2. `claim --job JOB_ID --owner WORKER_ID`; retain the returned lease JSON. A `null` result means no claim was granted.
3. `review-idea --job JOB_ID --input review.json` once for each reviewer role.
4. `record --job JOB_ID --lease lease.json --input artifact.json` for each rendition.
5. `review-artifact --job JOB_ID --format FORMAT --input qa.json` for each rendition.
6. `gate --job JOB_ID` to inspect, or `gate --job JOB_ID --lease lease.json` to attempt READY.
7. `manifest --job JOB_ID` and `status --job JOB_ID` to read evidence and ledger state.

Use `fail --job JOB_ID --lease lease.json --error DESCRIPTION --retryable` for a known retryable worker failure. Omit `--retryable` for a blocker. `resume --job JOB_ID` only requeues a repaired BLOCKED job within its attempt budget.

The Python `Ledger` API also exposes `heartbeat`, compare-and-swap `revise_source`, and the transport-free outbox sequence:

```text
prepare_outbox -> start_outbox -> external adapter call -> finish_outbox
                                     ambiguous result -> UNKNOWN
UNKNOWN -> actual remote lookup -> reconcile_outbox
```

Persist the intention before sending. A positive reconciliation needs the existing external ID and evidence; an absence reconciliation needs explicit `confirmed_absent=True` and evidence. A timeout is not proof of absence. `finish_outbox` rejects expired leases; use reconciliation after such a timeout.

For weekly selection:

```bash
python3 -B pipeline/atlas_pipeline.py --db /chosen/durable/path/atlas.sqlite3 roundup --brand security.ink --week-start 2026-11-23 --timezone America/Los_Angeles
```

The week start must be Monday in the chosen timezone. The first call freezes the cutoff and selection. Late completions are not silently appended on retry. There is no performance ranking without actual metrics, and READY is not described as published.

## Persistence and CI

SQLite durability depends on the actual filesystem/host chosen. A file in this interactive workspace is not proof of unattended service persistence. The ledger is intended for a durable local host; a fresh GitHub runner cannot inherit it unless the controller restores authoritative state. Do not use a transient runner SQLite database as the production backlog.

`ci-smoke.yml` is the manual-only template. The installed `.github/workflows/atlas-quality-smoke.yml` also runs on changes to this isolated implementation branch. It uses read-only repository permission and calls no account connectors or publication APIs. GitHub Actions run [46109786226](https://github.com/micahheaton/creator-studio/actions/runs/46109786226) completed successfully for commit `20d7d206a67c546ec97b3464ee0296b6beb94da6`. That run proves the gate tests and expected refusal diagnostic, not a production episode or connected publishing flight.

The scheduler, connected Airtable roundtrip, GitHub commits/builds, real render/media inspection, durable artifact transfer, and native platform operations require separate end-to-end evidence. `TEST_REPORT.md` states exactly what was verified locally.

## Actual media diagnostic

`media_smoke.py` renders three four-second H.264/AAC files from supplied before/after PNGs. Every frame is labeled PIPELINE DIAGNOSTIC. It checks dimensions, duration, frame count, full audio/video decode and a quiet generated test signal. Run `python3 -B pipeline/media_smoke.py --before /path/before.png --after /path/after.png --output /path/diagnostic`. FFmpeg, ffprobe, libx264 and drawtext are required. This is not creative editing, narration, a real application recording or listening QA; `production_ready` remains false. Generated media and logs must stay outside public source.
