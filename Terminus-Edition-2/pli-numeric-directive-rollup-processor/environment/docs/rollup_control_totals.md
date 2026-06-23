# Rollup Control Totals

`/app/config/radix_weights.psv` defines integer weighting for canonical `base_radix` values:

`base_radix|weight_numerator|weight_denominator|state`

Only `ACTIVE` rows with positive integer numerator and denominator apply. The weighted value for a rolled accumulator is `value_cents * weight_numerator / weight_denominator`; rows that do not divide evenly make their group fail control reconciliation.

`/app/config/control_totals.psv` defines expected group totals:

`stream_id|base_radix|segment_id|expected_count|expected_weighted_cents|tolerance_cents`

Groups are keyed by canonical `stream_id`, `base_radix`, and `segment_id`. A group is `CONTROL_OK` only when the actual row count equals `expected_count` and the absolute difference between actual and expected weighted cents is within `tolerance_cents`. Missing, malformed, disabled, or unconfigured controls are `CONTROL_HELD`.

`/app/out/rollup_controls.psv` uses:

`stream_id|base_radix|segment_id|actual_count|actual_weighted_cents|expected_count|expected_weighted_cents|tolerance_cents|status`
