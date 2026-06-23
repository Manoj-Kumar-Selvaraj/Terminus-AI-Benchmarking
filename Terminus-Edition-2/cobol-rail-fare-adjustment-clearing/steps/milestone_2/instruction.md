Continue the rail fare adjustment reconciler in `/app/src/fare_adjust_reconcile.cbl`. Preserve the established matching gates, report schema, fixed-width output trimming, source-row consumption, action ordering, and summary semantics.

Legacy action fare_class aliases must be normalized before matching and report output: `ST` means `STD`, `EX` means `EXP`, `SR` means `SNR`. Any other action fare_class value stays ineligible for matching. Matched rows report the canonical source fare_class; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/adjustment_report.csv` and `/app/out/adjustment_summary.txt` with the established schemas, status labels, trimmed CSV identifiers, blank unmatched `fare_class` fields, and summary keys. The `reason` column must still echo the trimmed raw action reason on every matched or unmatched row, including ineligible reason values.
