The workload manifest consistency auditor marks healthy rollouts as `DRIFTED`. Fix `/app/src/manifest_batch.pli`, `/app/src/manifest_rules.pli`, or the batch harness so `/app/data/rollout_checks.psv` reconciles against `/app/data/manifests.psv`.

Milestone 1 requires full agreement on `workload_id`, `namespace`, `selector_label`, `port_name`, and `probe_path`. A manifest row is eligible only when `state` equals `ELIGIBLE_STATE` from `/app/src/manifest_rules.pli`. The check row's `check_code` must match one of `REASON_1`, `REASON_2`, or `REASON_3` case-insensitively. Each manifest row may be consumed at most once. Preserve check order.

When multiple manifest rows qualify for one check, consume the candidate with the latest `applied_ts`; break ties by the earliest manifest row in file order.

Write `/app/out/manifest_report.csv` with columns `claim_id`, `workload_id`, `namespace`, `probe_path`, `port_name`, `selector_label`, `check_code`, and `status`. Emit canonical `port_name` from the matched manifest on `CONSISTENT` rows; leave `port_name` blank on `DRIFTED` rows. Write `/app/out/manifest_summary.txt` as `key=value` lines for `consistent_count`, `consistent_checks`, `drifted_count`, and `drifted_checks`, summing `selector_label` as integers.

Ignore `/app/config/rollout_windows.psv` for this milestone.

Status must be exactly `CONSISTENT` or `DRIFTED`.
