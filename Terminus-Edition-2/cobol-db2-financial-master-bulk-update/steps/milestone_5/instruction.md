# Milestone 5 - Enforce settlement-control provenance

Extend `/app/internal/finbulk/runner.go` and `/app/bin/run_finbulk.sh` with optional `--control PATH`, preserving all milestone 1-4 fixed-width, restart, lock, atomicity, and output behavior. Invocations without `--control` must remain compatible. The JSON control manifest contains `batch_id`, `business_date`, `source`, `expected_detail_count`, and `expected_financial_total`.

Before any mutation, require the manifest values to match the parsed header, detail count, and BAL trailer total. Malformed or mismatched manifests must exit non-zero and write `summary_<batch>.json` with status exactly `FAILED_CLOSED`. A previously settled batch ID with a different input SHA-256 must fail the same way without changing master, risk, ledger, audit, checkpoint, applied-event, pending-lock, reject, or settlement history. Continue writing `rejects_<batch>.dat` and `pending_locks_<batch>.json` beneath `--out`.

After a successful controlled run, persist `control_totals[batch_id]` with `status` exactly `SETTLED`, integer `detail_count`, integer `financial_total`, `input_sha256`, and the identifying manifest fields. A rerun with the same input hash is idempotent and must not duplicate side effects; a different hash must not overwrite the existing settlement record. Use deterministic simulator state rather than hardcoded sample data.
