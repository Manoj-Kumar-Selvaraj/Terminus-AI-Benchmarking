Finish the marina docking fee reversal reconciler in `/app/src/docking_reversal_reconcile.cbl` by applying calendar gates from `/app/config/harbor_calendar.txt` while preserving milestone 1-2 behavior.

Source dates are eligible only when the same date appears in the calendar file with the literal state `OPEN` compared case-insensitively; closed, missing, unlisted, or malformed dates are ineligible. All earlier matching gates still apply, including aliases, consumption, status `D`, reasons, and allowed categories.

When more than one unused source row matches an action, choose the eligible row with the latest source date. If source dates tie, choose the earliest source input row. Consumption is tracked by source row position, not by record id alone.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/docking_reversal_report.csv` and `/app/out/docking_reversal_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
