Continue the telehealth session credit reconciler in `/app/src/session_credit_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action visit_type aliases must be normalized before matching and report output: `GN` means `GEN`, `SC` means `SPC`, `UG` means `URG`. Matched rows report the canonical source visit_type; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/session_credit_report.csv` and `/app/out/session_credit_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
