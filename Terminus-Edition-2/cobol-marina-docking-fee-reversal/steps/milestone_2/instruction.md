Continue the marina docking fee reversal reconciler in `/app/src/docking_reversal_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action berth_type aliases must be normalized before matching and report output: `SP` means `SLP`, `DY` means `DRY`, `TN` means `TRN`. Matched rows report the canonical source berth_type; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/docking_reversal_report.csv` and `/app/out/docking_reversal_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
