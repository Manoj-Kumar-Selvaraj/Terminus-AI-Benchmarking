Continue the scooter ride surcharge reversal reconciler in `/app/src/scooter_surcharge_reconcile.cbl`. Keep milestone 1 matching, report schema, status labels, blank unmatched fields, action order, source-row consumption, and summary semantics.

Legacy action `zone_code` aliases must be normalized before matching and report output. The fixed-width action field may carry either the canonical three-letter code or a legacy two-character prefix: `CB` means `CBD`, `RE` means `RES`, and `UN` means `UNI`. When the action value is not already canonical, normalize by using the first two characters of the trimmed action `zone_code` as the alias key. Alias normalization is not a wildcard: after normalization, the canonical source `zone_code` and canonical action `zone_code` must still be exactly equal. Matched rows report the canonical source `zone_code`; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/scooter_surcharge_report.csv` and `/app/out/scooter_surcharge_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
