# Offline DB2 simulator contract

`/app/tools/db2_financial_sim.py` is the trusted local DB2-style simulator. It stores all tables in a JSON state file supplied by `--db`.

Modeled SQLCODEs:

- `0`: statement succeeded and may be committed.
- `+100`: no master row was found. This is a business reject, not a job ABEND.
- `-911`: lock timeout/deadlock. This is retryable; do not turn it into a reject or advance beyond the locked sequence.
- `-803`: duplicate applied event marker. Reruns must not duplicate committed side effects.
- `-530`: referential/business constraint failure. Credit-limit changes must fail atomically when this occurs.

Compatibility constraints:

- Keep `/app/bin/run_finbulk.sh` and its flags: `--batch`, `--input`, `--db`, `--out`, `--abend-after`, and optional `--control PATH`.
- Keep JSON table names: `master`, `risk`, `ledger`, `audit`, `rejects`, `pending_locks`, `checkpoint`, `applied_events`, and `control_totals`.
- Keep the fixed-width input and reject-output formats documented in `/app/docs/fixed_width_layout.md`.
- Simulated ABEND via `--abend-after` returns process status `66` after writing summary and checkpoint state.
- Retryable lock contention returns process status `75` with pending-lock evidence.
- Output files are `summary_<batch>.json`, `rejects_<batch>.dat`, and `pending_locks_<batch>.json` beneath `--out`.
- Summary status literals are `OK`, `FAILED_CLOSED`, `SIMULATED_ABEND`, and `RETRYABLE_LOCK`. Lock summaries include integer `pending_locks`.
- Do not replace the workflow with precomputed output files. The verifier runs generated batches and inspects the DB state.

## Settlement control manifest (milestone 5)

When `--control PATH` is supplied, the manifest JSON must contain:

- `batch_id`
- `business_date`
- `source`
- `expected_detail_count`
- `expected_financial_total`

Successful controlled runs persist `control_totals[batch_id]` with:

- `status` (`SETTLED` on success)
- `detail_count`
- `financial_total`
- `input_sha256`
- the identifying control fields above

Same batch id with a different input hash must write summary status `FAILED_CLOSED`; same payload reruns remain idempotent.
