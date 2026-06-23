The numeric directive rollup batch under `/app` is accepting malformed accumulator work and skipping valid lines after partial directive-key collisions. Repair the PL/I control deck so `/app/scripts/run_batch.sh` produces a clean rollup report.

Read `ELIGIBLE_STATE`, `REASON_*`, and `NEGATIVE_OPCODE_CODES` from `/app/src/rollup_rules.pli` at runtime. Do not hardcode values from the sample deck.

Directive and accumulator rows can roll up only when `line_id`, `stream_id`, `value_cents`, `base_radix`, and `segment_id` all agree after trimming, case folding, and alias canonicalization on `base_radix` and `segment_id`. Opcodes listed in comma-delimited `NEGATIVE_OPCODE_CODES` must carry negative `value_cents`; all other eligible opcodes must carry positive cents. Summary totals always use absolute values; keys still match signed cents exactly.

`value_cents` must be a signed integer on both sides when validation is enabled, and `ingest_ts` and `rollup_ts` must be numeric 14-digit timestamps. Empty keys, malformed numeric fields, malformed timestamps, unknown opcodes, ineligible directive states, and wrong sign/direction pairs must produce `SKIPPED` rows without crashing. Each directive row may be consumed at most once, accumulator order is preserved, and competing directive candidates use latest `ingest_ts`, then earliest directive input row.

Write `/app/out/rollup_report.csv` as **pipe-delimited** columns `claim_id|line_id|stream_id|check_segment|segment_id|value_cents|opcode|status`. `check_segment` echoes the accumulator `segment_id`; `ROLLED` rows emit the canonical directive `segment_id`; `SKIPPED` rows leave `segment_id` blank. Write `/app/out/rollup_summary.txt` with `rolled_count`, `rolled_total_cents`, `skipped_count`, and `skipped_total_cents` as integer `key=value` lines.

Ignore window, control-total, downstream, ledger, capacity, and sequence files for this repair.
