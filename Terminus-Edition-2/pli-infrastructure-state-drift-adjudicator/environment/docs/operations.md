# Infrastructure State Drift Adjudicator

Platform governance compares live scans in `/app/data/observed.psv` against the ideal state catalog in `/app/data/ideal.psv`. Policy constants are DCL declarations in `/app/src/drift_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/drift_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Ideal catalog** (`/app/data/ideal.psv`): `resource_id`, `resource_group`, `attr_hash`, `module_name`, `region_code`, `ideal_ts`, `state`, `kind_code`.

**Observed scans** (`/app/data/observed.psv`): `claim_id`, `resource_id`, `resource_group`, `attr_hash`, `module_name`, `scan_ts`, `scan_code`, `region_code`.

**Audit windows** (`/app/config/audit_windows.psv`, milestone 3): `resource_group`, `open_ts`, `close_ts`, `state`.

See `/app/docs/drift_matching.md` for alignment rules.

## Outputs

`/app/out/drift_report.csv`:

`claim_id|resource_id|resource_group|region_code|module_name|attr_hash|scan_code|status`

`/app/out/drift_summary.txt`:

`aligned_count`, `aligned_resources`, `drifted_count`, `drifted_resources`
