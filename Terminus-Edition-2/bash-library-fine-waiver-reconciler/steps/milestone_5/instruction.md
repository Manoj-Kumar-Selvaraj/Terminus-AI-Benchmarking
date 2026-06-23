Extend `/app/scripts/reconcile.sh` with a configurable open-day window driven by `/app/config/run_profile.ini`. Read integer `waiver_open_window_days` from that file (the shipped value is `2`). All milestone 1–4 behavior remains in force.

When both `waiver_date` and `due_date` columns are present, count `open` days listed in `/app/config/cutoff_calendar.txt` strictly after `waiver_date` through and including `due_date`. The match is eligible only when that count is less than or equal to `waiver_open_window_days`. Count only dates explicitly marked `open`; closed or absent calendar lines do not count toward the window. Same-day waiver and due dates count zero days.

Matched report rows must still emit canonical uppercase desks; unmatched rows leave `desk` blank. Summary amounts remain positive integer cents.

Continue to write `/app/out/waiver_report.csv` and `/app/out/waiver_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
