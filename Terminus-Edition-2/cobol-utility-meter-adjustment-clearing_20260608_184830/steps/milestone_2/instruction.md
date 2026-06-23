Continue the utility meter adjustment reconciler in `/app/src/meter_adjust_reconcile.cbl`. Keep milestone 1 matching, report schema, free-format COBOL compatibility, fixed-width output trimming, and summary semantics.

Legacy action rate_code aliases must be normalized before matching and report output: `RS` means `RES`, `CM` means `COM`, `IN` means `IND`. Matched rows report the canonical source rate_code; unmatched rows leave that column truly blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/meter_adjustment_report.csv` and `/app/out/meter_adjustment_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
