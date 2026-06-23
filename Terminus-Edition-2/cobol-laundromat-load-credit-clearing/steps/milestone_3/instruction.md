Finish `/app/src/laundry_credit_reconcile.cbl` with service-calendar controls from `/app/config/service_calendar.txt`. All milestone 1 and 2 field validation, alias, consumption, report, and summary rules still apply; the candidate-selection strategy is extended by the latest eligible source-date rule below.

Each nonblank calendar line is `YYYYMMDD=STATE`; trim whitespace and compare `STATE` case-insensitively. Only dates whose state is `OPEN` are eligible. Closed, missing, unlisted, or non-numeric source dates are ineligible.

When multiple unused source rows qualify, choose the row with the latest eligible source date; tied dates use the earliest source input row. Consumption is tracked by source row position, not record id alone.

Matched report rows must include the selected source row's `source_date` in the `source_date` column; leave `source_date` blank on unmatched rows.

Continue writing `/app/out/laundry_credit_report.csv` and `/app/out/laundry_credit_summary.txt` with the same schemas, status labels, blank unmatched `machine_size` and `source_date`, raw zero-padded 10-character CSV `amount_cents`, and positive unpadded summary totals.
