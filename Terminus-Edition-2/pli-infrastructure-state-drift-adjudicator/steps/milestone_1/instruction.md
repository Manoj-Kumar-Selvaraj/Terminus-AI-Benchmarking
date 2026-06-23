The infrastructure state drift adjudicator aligns too many scans on partial resource keys. Fix `/app/src/drift_batch.pli`, `/app/src/drift_rules.pli`, or the batch harness so `/app/data/observed.psv` reconciles against `/app/data/ideal.psv`.

Milestone 1 requires full agreement on `resource_id`, `resource_group`, `attr_hash`, `module_name`, and `region_code`. An ideal row is eligible only when `state` equals `ELIGIBLE_STATE` from `/app/src/drift_rules.pli`. The scan row's `scan_code` must match one of `REASON_1`, `REASON_2`, or `REASON_3` case-insensitively. Each ideal row may be consumed at most once. Preserve scan order.

When multiple ideal rows qualify for one scan, consume the candidate with the latest `ideal_ts`; break ties by the earliest ideal row in file order.

Write `/app/out/drift_report.csv` with columns `claim_id`, `resource_id`, `resource_group`, `region_code`, `module_name`, `attr_hash`, `scan_code`, and `status`. Emit canonical `module_name` from the matched ideal row on `ALIGNED` rows; leave `module_name` blank on `DRIFTED` rows. Write `/app/out/drift_summary.txt` as `key=value` lines for `aligned_count`, `aligned_resources`, `drifted_count`, and `drifted_resources`, summing `attr_hash` as integers.

Ignore `/app/config/audit_windows.psv` for this milestone.

Status must be exactly `ALIGNED` or `DRIFTED`.
