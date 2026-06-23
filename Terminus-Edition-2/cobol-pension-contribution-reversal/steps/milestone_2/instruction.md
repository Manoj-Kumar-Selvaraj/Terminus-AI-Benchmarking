Continue the pension contribution reversal reconciler in `/app/src/pension_reversal_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action bucket aliases must be normalized before matching and report output: `EE` means `EMP`, `ER` means `ERD`, `VL` means `VOL`. Matched rows report the canonical source bucket; unmatched rows leave that column blank. Each source row can still be consumed at most once. When duplicate action rows target the same source row, the earliest eligible action in reversal input order wins regardless of action date.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/reversal_report.csv` and `/app/out/reversal_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
