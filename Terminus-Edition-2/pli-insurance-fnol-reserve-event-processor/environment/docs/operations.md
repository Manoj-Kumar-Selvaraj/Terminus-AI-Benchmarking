# Insurance FNOL Reserve Adjustment

Batch entrypoint: `/app/scripts/run_batch.sh` (runs `gawk -f /app/scripts/pli_fnol.awk`).

## Input files

- `/app/data/claims.psv` — source FNOL reserve rows
- `/app/data/adjustments.psv` — reserve adjustment actions
- `/app/src/fnol_batch.pli` — `%SET` control flags
- `/app/src/fnol_rules.pli` — `DCL ... INIT(...)` rule constants
- `/app/config/windows.psv` — `loss_unit|open_ts|close_ts|state` (M2+)
- `/app/config/policy_limits.psv` — `policy_id|max_reserve_cents` (M4)
- `/app/config/subrogation_holds.psv` — `action_id|hold_reason` (M4)
- `/app/state/reserve_ledger.psv` — committed reserve evidence (M3+)
- `/app/state/restart_checkpoint.txt` — integer checkpoint row count (M3+)

## Report CSV

`/app/out/reserve_adjustment_report.csv` pipe-delimited columns (exact order):

`action_id|claim_id|policy_id|loss_unit|coverage_type|reserve_cents|reason|status`

Status is exactly `MATCHED` or `UNMATCHED`. Unmatched rows leave `coverage_type` blank.

## Summary file

`/app/out/reserve_adjustment_summary.txt` key=value lines:

- `matched_count=<int>`
- `matched_amount_cents=<int>` (non-negative absolute total)
- `unmatched_count=<int>`
- `unmatched_amount_cents=<int>` (non-negative absolute total)

## Ledger (M3+)

`/app/out/reserve_ledger.psv` header:

`action_id|claim_id|policy_id|loss_unit|coverage_type|reserve_cents|status`

## Restart audit (M3+)

`/app/out/restart_audit.txt`:

- `checkpoint_status=OK|MISSING|STALE|AHEAD`
- `committed_rows=<int>` (new committed rows this run)

## Exceptions (M4)

`/app/out/reserve_exceptions.csv` header:

`action_id|claim_id|policy_id|reason|detail`

## Reserve position (M4)

`/app/out/reserve_position.txt` header:

`policy_id|limit_cents|used_cents|remaining_cents`
