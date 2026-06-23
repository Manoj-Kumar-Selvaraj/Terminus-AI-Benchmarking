Finish the scooter ride surcharge reversal reconciler in `/app/src/scooter_surcharge_reconcile.cbl` by applying calendar gates from `/app/config/fleet_calendar.txt` while preserving milestone 1-2 behavior.

Source dates are eligible only when the source date is numeric, the same date appears in the calendar file, and the calendar state equals `OPEN` when compared case-insensitively (for example `open`, `Open`, and `oPeN` are all eligible). Closed, missing, unlisted, blank, or non-numeric source dates are ineligible even if the calendar file lists them. The action date must also be numeric and must be on or after the candidate source date. `/app/config/fleet_calendar.txt` uses one line per date in the form `YYYYMMDD=STATE` (for example `20260501=OPEN`); compare STATE to `OPEN` case-insensitively. All earlier matching gates still apply, including milestone 2 `zone_code` aliases (`CB`→`CBD`, `RE`→`RES`, `UN`→`UNI`), source-row consumption, source status `Z`, eligible reasons, branch equality, exact amount equality, and allowed categories.

When more than one unused source row matches an action, choose the eligible row with the latest source date. If source dates tie, choose the earliest source input row. Consumption is tracked by source row position, not by record id alone.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/scooter_surcharge_report.csv` and `/app/out/scooter_surcharge_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
