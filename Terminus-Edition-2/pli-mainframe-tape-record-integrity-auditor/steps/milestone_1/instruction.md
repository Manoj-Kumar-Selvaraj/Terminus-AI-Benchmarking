The mainframe tape record integrity auditor accepts partial record matches. Repair the editable PL/I control decks in `/app/src/tape_batch.pli` and `/app/src/tape_rules.pli` so `/app/data/tape_audits.psv` reconciles against `/app/data/tape_catalog.psv`. Read the `DCL ... INIT('value')` declarations from the rule deck at runtime rather than hardcoding the shipped values.

A catalog row qualifies only when all trimmed, case-insensitive values for `record_id`, `volume_id`, positive integer `length_hash`, `block_no`, and `reel_id` equal the audit row. Its `state` must equal `ELIGIBLE_STATE`, and the audit `verdict_code` must equal `REASON_1`, `REASON_2`, or `REASON_3` case-insensitively. `recv_ts` must be a numeric 14-digit timestamp. Preserve audit order and consume each catalog row at most once.

Write `/app/out/tape_report.csv` as pipe-separated text with this exact header:

`claim_id|record_id|volume_id|reel_id|block_no|length_hash|verdict_code|status`

For `VERIFIED`, emit the selected catalog row's canonical `block_no`. For `CORRUPT`, leave `block_no` blank. Use only `VERIFIED` and `CORRUPT` as status values.

Write `/app/out/tape_summary.txt` as exactly four `key=value` lines: `verified_count`, `verified_blocks`, `corrupt_count`, and `corrupt_blocks`. The block totals sum the positive integer `length_hash` values from audit rows in the corresponding status group.

Do not apply `/app/config/mount_windows.psv` yet.
