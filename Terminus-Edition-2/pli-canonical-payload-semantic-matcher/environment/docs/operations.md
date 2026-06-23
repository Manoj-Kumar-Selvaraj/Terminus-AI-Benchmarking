# Canonical Payload Semantic Matcher

Nightly regression compares producer field snapshots in `/app/data/actual.psv` against the canonical expected catalog in `/app/data/expected.psv`. Policy constants are DCL declarations in `/app/src/semantic_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/semantic_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Expected catalog** (`/app/data/expected.psv`): `field_id`, `schema_id`, `payload_hash`, `tolerance_key`, `segment_id`, `recv_ts`, `state`, `kind_code`.

**Actual checks** (`/app/data/actual.psv`): `claim_id`, `field_id`, `schema_id`, `payload_hash`, `tolerance_key`, `check_ts`, `mode_code`, `segment_id`.

**Compare windows** (`/app/config/compare_windows.psv`, milestone 3): `schema_id`, `open_ts`, `close_ts`, `state`.

See `/app/docs/compare_semantics.md` for matching rules and alias behavior.

## Outputs

`/app/out/semantic_report.csv` — one row per actual check, preserving input order:

`claim_id|field_id|schema_id|check_segment|segment_id|payload_hash|mode_code|status`

`check_segment` echoes the segment id submitted on the actual row. `segment_id` carries the canonical emitted value on `EQUAL` rows and is blank on `DIFFER` rows.

`/app/out/semantic_summary.txt` — totals:

`equal_count`, `equal_fields`, `differ_count`, `differ_fields`
