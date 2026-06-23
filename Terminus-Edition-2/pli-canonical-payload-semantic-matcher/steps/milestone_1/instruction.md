The canonical payload semantic matcher marks too many field checks as `DIFFER`. Fix `/app/src/semantic_batch.pli`, `/app/src/semantic_rules.pli`, or the batch harness so `/app/data/actual.psv` reconciles against `/app/data/expected.psv`.

Milestone 1 requires full agreement on `field_id`, `schema_id`, `payload_hash`, `tolerance_key`, and `segment_id`. An expected row is eligible only when `state` equals `ELIGIBLE_STATE` from `/app/src/semantic_rules.pli`. The actual row's `mode_code` must match one of `REASON_1`, `REASON_2`, or `REASON_3` case-insensitively. Each expected row may be consumed at most once. Preserve actual-row order.

When multiple expected rows qualify for one actual row, consume the candidate with the latest `recv_ts`; break ties by the earliest expected row in file order.

Write `/app/out/semantic_report.csv` with columns `claim_id`, `field_id`, `schema_id`, `segment_id`, `payload_hash`, `mode_code`, and `status`. Emit canonical `segment_id` from the matched expected row on `EQUAL` rows; leave `segment_id` blank on `DIFFER` rows. Write `/app/out/semantic_summary.txt` as `key=value` lines for `equal_count`, `equal_fields`, `differ_count`, and `differ_fields`, summing `payload_hash` as integers.

Ignore `/app/config/compare_windows.psv` for this milestone.

Status must be exactly `EQUAL` or `DIFFER`.
