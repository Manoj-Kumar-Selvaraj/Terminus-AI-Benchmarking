The auditor must enforce `/app/config/mount_windows.psv`, whose columns are `volume_id|open_ts|close_ts|state`. Keep all existing full-key, alias, eligibility, ordering, consumption, report, and summary behavior.

`recv_ts`, `audit_ts`, `open_ts`, and `close_ts` must each be numeric 14-digit UTC timestamps. A catalog candidate qualifies only when one window has the same trimmed, case-insensitive `volume_id`, its state equals `OPEN_MOUNT_STATE` case-insensitively, the window is not reversed, and both timestamps fall inside that same inclusive window. Also require `recv_ts <= audit_ts`. Missing, malformed, closed, unlisted, wrong-volume, before-open, after-close, and reversed cases are `CORRUPT`.

When several unused candidates qualify, choose the greatest `recv_ts`, then the earliest catalog input row. Consumption carries across audits in audit input order.

Continue writing pipe-separated `/app/out/tape_report.csv` with header `claim_id|record_id|volume_id|reel_id|block_no|length_hash|verdict_code|status` and `/app/out/tape_summary.txt` with exactly `verified_count`, `verified_blocks`, `corrupt_count`, and `corrupt_blocks`. Emit canonical `block_no` only for `VERIFIED`, blank it for `CORRUPT`, and use only those two status values.
