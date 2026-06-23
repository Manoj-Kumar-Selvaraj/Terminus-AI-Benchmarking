# Workload Manifest Consistency Auditor

Cluster rollout verification compares probe checks in `/app/data/rollout_checks.psv` against declared manifests in `/app/data/manifests.psv`. Policy constants are DCL declarations in `/app/src/manifest_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/manifest_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Manifest catalog** (`/app/data/manifests.psv`): `workload_id`, `namespace`, `selector_label`, `port_name`, `probe_path`, `applied_ts`, `state`, `kind_code`.

**Rollout checks** (`/app/data/rollout_checks.psv`): `claim_id`, `workload_id`, `namespace`, `selector_label`, `port_name`, `check_ts`, `check_code`, `probe_path`.

**Rollout windows** (`/app/config/rollout_windows.psv`, milestone 3): `namespace`, `open_ts`, `close_ts`, `state`.

See `/app/docs/manifest_matching.md` for consistency rules.

## Outputs

`/app/out/manifest_report.csv`:

`claim_id|workload_id|namespace|probe_path|port_name|selector_label|check_code|status`

`/app/out/manifest_summary.txt`:

`consistent_count`, `consistent_checks`, `drifted_count`, `drifted_checks`
