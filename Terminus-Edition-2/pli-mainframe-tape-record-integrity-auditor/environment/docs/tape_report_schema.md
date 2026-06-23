# Tape Report Schema

`/app/out/tape_report.csv` must use this exact pipe-delimited header:

`claim_id|record_id|volume_id|reel_id|block_no|length_hash|verdict_code|status`

Rules:
- One output row per audit input row in audit-file order.
- `status` is exactly `VERIFIED` or `CORRUPT`.
- `VERIFIED` rows emit canonical `block_no` from the consumed catalog row.
- `CORRUPT` rows leave `block_no` blank.
- Other columns echo the audit row except where canonicalization applies to matching only.
