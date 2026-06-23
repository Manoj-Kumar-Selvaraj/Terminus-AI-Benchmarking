Extend `/app/lib/reconcile.rb` with a configurable open-day window driven by `/app/config/run_profile.ini`. Read integer `deposit_open_window_days` from that file (the shipped value is `2`). All milestone 1–4 behavior remains in force.

When both `deposit_date` and `return_date` columns are present, count `open` days listed in `/app/config/cutoff_calendar.txt` strictly after `deposit_date` through and including `return_date`. The match is eligible only when that count is less than or equal to `deposit_open_window_days`. Count only dates explicitly marked `open`; closed or absent calendar lines do not count toward the window. Same-day deposit and return dates count zero days.

Matched report rows must still emit canonical keg types; unmatched rows leave `keg_type` blank. Summary amounts remain positive integer cents.

Continue to write `/app/out/deposit_report.csv` and `/app/out/deposit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
