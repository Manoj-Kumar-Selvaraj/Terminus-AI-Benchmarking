Continue the zoo admission refund reconciler in `/app/src/zoo_refund_reconcile.cbl`. Keep milestone 1 matching, report schema, and summary semantics.

Legacy action ticket_tier aliases must be normalized before matching and report output. The fixed-width action field may carry either the canonical three-letter code or a legacy two-character prefix: `AD` means `ADT`, `CH` means `CHD`, and `SE` means `SEN`. When the action value is not already canonical, normalize by using the first two characters of the trimmed action ticket_tier as the alias key. Matched rows report the canonical source ticket_tier; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/zoo_refund_report.csv` and `/app/out/zoo_refund_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
