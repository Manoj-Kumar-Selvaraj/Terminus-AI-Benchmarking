# Milestone 2 — Make reruns checkpoint-safe and idempotent

After the baseline repair, reruns after an ABEND still duplicate committed ledger, audit, and balance changes.

Continue in `/app`, review `/app/docs/restart_runbook.md`, and repair `/app/internal/finbulk/profile.go` and `/app/internal/finbulk/runner.go`. Preserve milestone 1.

For this milestone, make the FNBULKUP Go driver restartable and idempotent:

- a simulated ABEND triggered by `--abend-after` must persist only fully committed records;
- the ABEND path must return process status `66` after writing `summary_<batch>.json` with status exactly `SIMULATED_ABEND` and persisting checkpoint/applied-event state through the last fully committed detail;
- rerunning the same batch must skip already committed detail records without duplicating master changes, ledger rows, or audit rows;
- duplicate sequence events within the same batch must be counted as skipped, then processing must continue with later details rather than failing the batch;
- checkpoint/applied-event state must retain the documented DB2 simulator JSON schema;
- a completed batch rerun must be safe and leave state stable.

Do not delete audit history or reset the database to make a rerun look clean. The verifier checks state before and after reruns.
