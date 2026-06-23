# Retail Batch Trailer Reconciler

End-of-day settlement compares trailer claims in `/app/data/trailer_claims.psv` against posted batches in `/app/data/batches.psv`. Policy constants are DCL declarations in `/app/src/trailer_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/trailer_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Batch file** (`/app/data/batches.psv`): `batch_id`, `account_no`, `net_cents`, `dc_flag`, `branch_id`, `posted_ts`, `state`, `kind_code`.

**Trailer claims** (`/app/data/trailer_claims.psv`): `claim_id`, `batch_id`, `account_no`, `net_cents`, `dc_flag`, `claim_ts`, `reason_code`, `branch_id`.

**Settlement windows** (`/app/config/settlement_windows.psv`, milestone 3): `account_no`, `open_ts`, `close_ts`, `state`.

See `/app/docs/trailer_matching.md`.

## Outputs

`/app/out/trailer_report.csv`: `claim_id|batch_id|account_no|branch_id|dc_flag|net_cents|reason_code|status`

`/app/out/trailer_summary.txt`: `balanced_count`, `balanced_amount_cents`, `rejected_count`, `rejected_amount_cents`
