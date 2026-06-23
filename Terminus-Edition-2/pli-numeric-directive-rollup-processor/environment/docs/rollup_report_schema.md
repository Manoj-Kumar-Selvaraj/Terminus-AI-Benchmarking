# Rollup Report Schema

`/app/out/rollup_report.csv` must use this exact pipe-delimited header:

`claim_id|line_id|stream_id|check_segment|segment_id|value_cents|opcode|status`

Rules:
- One output row per accumulator input row in accumulator-file order.
- `status` is exactly `ROLLED` or `SKIPPED`.
- `check_segment` echoes the accumulator row's `segment_id`.
- `ROLLED` rows emit canonical `segment_id` from the consumed directive row.
- `SKIPPED` rows leave `segment_id` blank.
