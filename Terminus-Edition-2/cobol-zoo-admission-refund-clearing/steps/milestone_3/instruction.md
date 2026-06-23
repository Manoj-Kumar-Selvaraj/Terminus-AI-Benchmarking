Finish the zoo admission refund reconciler in `/app/src/zoo_refund_reconcile.cbl` by applying calendar gates from `/app/config/gate_calendar.txt` while preserving milestone 1-2 behavior.

Source dates are eligible only when the source date is numeric, the same date appears in the calendar file, and the calendar state equals `OPEN` when compared case-insensitively (for example `open`, `Open`, and `oPeN` are all eligible). Closed, missing, unlisted, or non-numeric source dates are ineligible even if the calendar file lists them. All earlier matching gates still apply, including aliases, consumption, status `A`, reasons, and allowed categories.

When more than one unused source row matches an action, choose the eligible row with the latest source date. If source dates tie, choose the earliest source input row. Consumption is tracked by source row position, not by record id alone.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/zoo_refund_report.csv` and `/app/out/zoo_refund_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
