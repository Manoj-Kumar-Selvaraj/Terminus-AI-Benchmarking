# Downstream Delivery Contract

The downstream delivery package is written under `/app/out/downstream/`.

Accepted groups:

`accepted_rollups.psv`

`stream_id|base_radix|segment_id|rolled_count|rolled_total_cents|weighted_total_cents`

Rejected accumulator rows:

`rejected_rollups.psv`

`claim_id|line_id|stream_id|segment_id|reject_code|value_cents`

Manifest:

`manifest.json`

The manifest is a single JSON object with schema version `rollup-downstream/v1` and integer fields `accepted_groups`, `accepted_rows`, `rejected_rows`, `accepted_total_cents`, and `weighted_total_cents`.

Rows that never rolled use reject code `SKIPPED_INPUT`. Rows that rolled into a group with failed control totals use reject code `CONTROL_HELD`.
