# Numeric Directive Rollup Processor

Batch analytics rolls accumulator lines in `/app/data/accumulators.psv` against signed directives in `/app/data/directives.psv`. Policy constants are DCL declarations in `/app/src/rollup_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/rollup_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Directives** (`/app/data/directives.psv`): `line_id`, `stream_id`, `value_cents`, `base_radix`, `segment_id`, `ingest_ts`, `state`, `kind_code`, optional `seq_no`.

**Accumulators** (`/app/data/accumulators.psv`): `claim_id`, `line_id`, `stream_id`, `value_cents`, `base_radix`, `rollup_ts`, `opcode`, `segment_id`, optional `expected_seq`, optional `netting_key`.

**Rollup windows** (`/app/config/rollup_windows.psv`): `stream_id`, `open_ts`, `close_ts`, `state`.

**Radix weights** (`/app/config/radix_weights.psv`): `base_radix`, `weight_numerator`, `weight_denominator`, `state`.

**Control totals** (`/app/config/control_totals.psv`): `stream_id`, `base_radix`, `segment_id`, `expected_count`, `expected_weighted_cents`, `tolerance_cents`.

**Rollup calendar** (`/app/config/rollup_calendar.psv`): `business_date`, `cutoff_ts`, `state`.

**Stream capacity** (`/app/config/stream_capacity.psv`): `stream_id`, `base_radix`, `limit_cents`.

**Directive holds** (`/app/config/directive_holds.psv`): `claim_id`, `hold_reason`.

**Sequence locks** (`/app/config/sequence_locks.psv`): `stream_id`, `segment_id`, `required_seq`, `max_gap`.

**Ledger state** (`/app/state/rollup_ledger.psv`): committed rollup evidence.

**Restart checkpoint** (`/app/state/restart_checkpoint.txt`): committed row count marker.

**Group commits** (`/app/state/rollup_commits.psv`): append-only committed group evidence.

See `/app/docs/rollup_matching.md`, `/app/docs/rollup_alias_rules.md`, `/app/docs/rollup_window_rules.md`, `/app/docs/rollup_control_totals.md`, and `/app/docs/downstream_delivery_contract.md`.

## Outputs

**Report** (`/app/out/rollup_report.csv`): pipe-delimited; see `/app/docs/rollup_report_schema.md`.

**Summary** (`/app/out/rollup_summary.txt`): `rolled_count`, `rolled_total_cents`, `skipped_count`, `skipped_total_cents` using absolute cents.

**Controls** (`/app/out/rollup_controls.psv`): weighted group reconciliation when enabled.

**Downstream** (`/app/out/downstream/`): accepted/rejected PSV plus `manifest.json`.

**Ledger** (`/app/out/rollup_ledger.psv`): updated committed ledger when ledger mode is on.

**Restart audit** (`/app/out/restart_audit.txt`): checkpoint status and committed row count.

**Exceptions** (`/app/out/rollup_exceptions.csv`): holds, replay duplicates, capacity, netting.

**Capacity position** (`/app/out/capacity_position.txt`): stream radix limits and usage.

**Group commits** (`/app/out/rollup_commits.psv`): newly committed control-OK groups.
