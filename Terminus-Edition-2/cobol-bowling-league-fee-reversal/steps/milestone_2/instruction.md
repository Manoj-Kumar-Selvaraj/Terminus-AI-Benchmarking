Continue the bowling league fee reversal reconciler in `/app/src/league_fee_reversal_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action lane_type aliases must be normalized before matching and report output. The fixed-width action field may carry either the canonical three-letter code or a legacy two-character prefix: `ST` means `STR`, `SC` means `SCR`, and `CO` means `COS`. When the action value is not already canonical, normalize by using the first two characters of the trimmed action lane_type as the alias key. Matched rows report the canonical source lane_type; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/league_reversal_report.csv` and `/app/out/league_reversal_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
