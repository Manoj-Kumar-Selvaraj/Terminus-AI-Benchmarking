Continue the warehouse storage credit reconciler in `/app/src/storage_credit_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action charge_type aliases must be normalized before matching and report output: `BN` means `BIN`, `FT` means `FLT`, `CD` means `CLD`. Matched rows report the canonical source charge_type; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
