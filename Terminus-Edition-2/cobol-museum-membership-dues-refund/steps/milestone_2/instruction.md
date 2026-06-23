Continue the museum membership dues refund reconciler in `/app/src/membership_refund_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action plan_code aliases must be normalized before matching and report output: `AN` means `ANN`, `FM` means `FAM`, `SU` means `STU`. Matched rows report the canonical source plan_code; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/dues_refund_report.csv` and `/app/out/dues_refund_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
