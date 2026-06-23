Extend `/app/cmd/reconcile/main.go` while preserving every milestone 1 and milestone 2 rule and output schema.

When multiple unused bid rows satisfy all matching rules for one reversal, choose the row with the latest eligible bid `event_ts`. If timestamps tie, choose the earliest bid input row. Consumption is by physical bid row position, not by `bid_id` alone.

Continue reading `/app/config/session_windows.csv` at runtime with trimmed, case-insensitive `OPEN` state, in-window bid timestamps, and reversal timestamps on or after the bid and not after window close.

Keep `/app/out/reversal_report.csv` and `/app/out/reversal_summary.txt` schemas, ordering, canonical channel output, blank unmatched channels, and positive amount accounting unchanged.

Compile with `/usr/local/go/bin/go`.
