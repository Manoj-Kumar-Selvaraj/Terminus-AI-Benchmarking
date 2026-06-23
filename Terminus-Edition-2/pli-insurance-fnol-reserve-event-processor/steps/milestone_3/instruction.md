The FNOL reserve batch now runs during restart after an interrupted settlement cycle. Continue through `/app/scripts/run_batch.sh` and preserve all milestone 1 and milestone 2 behavior.

Use `/app/state/reserve_ledger.psv` as committed-state evidence. Its exact header is `action_id|claim_id|policy_id|loss_unit|coverage_type|reserve_cents|status`. Rows with status `COMMITTED` represent adjustments that must not match again in the current run. A replay duplicate is identified by the committed `action_id`, `claim_id`, `policy_id`, and `loss_unit` combination. Duplicates must be `UNMATCHED` in `/app/out/reserve_adjustment_report.csv`, must not create a second ledger row, and must add a `REPLAY_DUPLICATE` row to `/app/out/reserve_exceptions.csv` when exception output is enabled by later milestones.

Use `/app/state/restart_checkpoint.txt` as checkpoint evidence. If the checkpoint is missing, nonnumeric, stale, or ahead of the ledger row count, processing must continue deterministically and `/app/out/restart_audit.txt` must report `checkpoint_status=MISSING`, `STALE`, `AHEAD`, or `OK` plus `committed_rows=<integer>` for new committed rows.

Write `/app/out/reserve_ledger.psv` with the same ledger header, preserving existing committed rows first and appending only newly matched rows from the current run. Repeated runs over the same state must be idempotent.
