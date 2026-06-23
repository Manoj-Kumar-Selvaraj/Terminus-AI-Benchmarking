The retail batch trailer reconciler rejects balanced settlement batches on partial key matches. Fix `/app/src/trailer_batch.pli`, `/app/src/trailer_rules.pli`, or the batch harness so `/app/data/trailer_claims.psv` reconciles against `/app/data/batches.psv`.

Milestone 1 requires full agreement on `batch_id`, `account_no`, `net_cents`, `dc_flag`, and `branch_id`. A batch row is eligible only when `state` equals `ELIGIBLE_STATE` from `/app/src/trailer_rules.pli`. The claim row's `reason_code` must match one of `REASON_1`, `REASON_2`, or `REASON_3` case-insensitively. Each batch row may be consumed at most once. Preserve claim order.

When multiple batch rows qualify for one claim, consume the candidate with the latest `posted_ts`; break ties by the earliest batch row in file order.

Write `/app/out/trailer_report.csv` with columns `claim_id`, `batch_id`, `account_no`, `branch_id`, `dc_flag`, `net_cents`, `reason_code`, and `status`. Emit canonical `dc_flag` from the matched batch on `BALANCED` rows; leave `dc_flag` blank on `REJECTED` rows. Write `/app/out/trailer_summary.txt` as `key=value` lines for `balanced_count`, `balanced_amount_cents`, `rejected_count`, and `rejected_amount_cents`, summing `net_cents` as integers.

Ignore `/app/config/settlement_windows.psv` for this milestone.

Status must be exactly `BALANCED` or `REJECTED`.
