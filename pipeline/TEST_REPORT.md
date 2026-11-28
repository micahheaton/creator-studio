# Atlas gate engine - local verification report

Executed in the provided Linux workspace on **2026-11-28 UTC**, using **Python 3.12.14**. No external service was read or changed by these tests.

## Results

**Eight tests passed** (`unittest`, 0.178 seconds on the recorded run). These are logic tests using explicitly labeled fixture reviews and storage receipts. They are not connected production acceptance tests.

| Test | Verified behavior |
|---|---|
| Idempotent intake, leases, bounded retries | Duplicate intake returns one job; a second SQLite connection cannot steal an active claim; recovery fences the old worker; retry delay and attempt ceiling are enforced. |
| Independent review and evidence mode | Builder self-approval is rejected; one reviewer cannot fill all three board roles; fixture evidence cannot pass the ordinary manifest gate. |
| Source change | A source revision invalidates existing QA/artifact eligibility and the prior worker lease. |
| Corruption and storage receipt | A wrong read-back checksum blocks eligibility; altering approved local bytes blocks READY. |
| Required formats and media observations | Missing video blocks; a text storyboard cannot be treated as video; missing motion/audio inspection blocks. |
| Revised brief and stale edition | A new brief supersedes earlier READY work, blocks its pending draft intent, and marks a cached roundup stale. |
| Draft intent identity and uncertain outcomes | Re-reviewing identical content does not create a second intent; exact payload persists; expired sending state becomes UNKNOWN; reconciliation reuses the existing external ID without another send. |
| Weekly selection | Only READY content is included; the DST-transition week has 169 actual hours; absent metrics remain null; repeated calls preserve the same edition. |

## Deterministic smoke

The smoke generated a labeled diagnostic HTML file and a text storyboard, registered their real local byte hashes, then attempted READY.

**Expected state: BLOCKED. Actual state: BLOCKED.**

The gate returned 28 reasons including fixture-only idea reviews, absent UI/motion/audio QA, no genuine durable receipts, and the fact that the storyboard is not rendered video. The diagnostic exits 0 because this rejection is the intended result.

Smoke report fields explicitly include:

```json
{
  "diagnostic_passed": true,
  "production_ready": false,
  "connected_end_to_end_tested": false,
  "source_commit_verified": false,
  "real_motion_audio_ui_qa_performed": false,
  "durable_upload_performed": false,
  "platform_draft_created": false,
  "scheduler_execution_tested": false
}
```

The diagnostic SQLite database was then reopened by the CLI and returned `BLOCKED`. Standalone validation of its saved manifest exited **2**, correctly refusing eligibility. This verifies persistence across local process invocations, not persistence across interactive sessions or hosted runner lifetimes.

Generated evidence is under `pipeline/_smoke/` and is excluded from source control by default. `smoke_report.json`, `diagnostic_manifest.json`, and `diagnostic.sqlite3` are diagnostics only.

## Independent review and corrections

A separate agent inspected the initial implementation and reproduced two gate failures with in-memory fixture data: a revised brief did not invalidate the earlier READY job, and changed review metadata generated a second draft intent for identical content. Both were corrected and received regression coverage. The review also identified missing payload persistence; the outbox now retains canonical payload JSON and verifies its hash before sending.

The initial reviewer did not re-review the final code. The final corrections were exercised by the test suite described above.

## Not established

No Airtable update, GitHub workflow run, actual source commit verification, browser interaction review, media playback/listening review, durable remote upload/read-back, native platform draft, public post, weekly publication, scheduler installation, or recurring background execution is established by this report. The engine validates supplied evidence and exact local bytes; connected adapters must supply genuine evidence for those legs.
