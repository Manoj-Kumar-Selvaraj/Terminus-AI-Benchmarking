The adjudicator is now run during restart after an interrupted treasury settlement batch. Continue to run it through `/app/scripts/run_batch.sh` and preserve all milestone 1 and milestone 2 behavior.

Enable ledger output in `/app/src/wire_batch.pli` with `LEDGER_MODE=ON` so the batch emits `/app/out/wire_ledger.psv` and related restart artifacts during this milestone.

Use `/app/state/wire_ledger.psv` as committed-state evidence. Its exact header is `claim_id|wire_id|account|branch_id|rail_code|amount_cents|status`. Rows with status `COMMITTED` represent wires that must not be cleared again in the current run. A replay duplicate is identified by the committed `claim_id`, `wire_id`, `account`, and `branch_id` combination. Duplicates must be returned in `/app/out/wire_report.csv`, must not create a second ledger row, and must add a `REPLAY_DUPLICATE` row to `/app/out/wire_exceptions.csv` when exception output is enabled by later milestones.

Use `/app/state/restart_checkpoint.txt` as checkpoint evidence. If the checkpoint is missing, nonnumeric, stale, or ahead of the ledger length, processing must continue deterministically and `/app/out/restart_audit.txt` must report `checkpoint_status=MISSING`, `STALE`, `AHEAD`, or `OK` plus `committed_rows=<integer>` for new committed rows.

Write `/app/out/wire_ledger.psv` with the same ledger header, preserving existing committed rows first and appending only newly cleared rows from the current run. Repeated runs over the same state must be idempotent: already committed rows stay committed once, and new rows are not duplicated.
