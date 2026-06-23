Operations now requires dispatch-calendar eligibility during courier credit processing. Update `/app/src/parcel_credit_reconcile.cbl` so `/app/scripts/run_batch.sh` applies `/app/config/dispatch_calendar.txt` while preserving the established matching, alias, consumption, report, and summary behavior.

Each input record starts with a one-byte record type prefix. The `record_id` starts after that prefix; do not include the leading `S` or `A` byte in comparisons or report output. The program is compiled as free-format COBOL with `cobc -x -free -O2`, so rewritten code and comments must be valid in free-format COBOL. The report `status` column must contain only `MATCHED` or `UNMATCHED`; unmatched rows leave `service_tier` blank.

Source dates are eligible only when the same date appears in the calendar file with the literal state `OPEN` compared case-insensitively; closed, missing, unlisted, or malformed dates are ineligible. All earlier matching gates still apply, including aliases, consumption, status `S`, reasons, and allowed categories.

When more than one unused source row matches an action, choose the eligible row with the latest source date. Consumption is tracked by source row position, not by record id alone.

Continue to write `/app/out/surcharge_credit_report.csv` and `/app/out/surcharge_credit_summary.txt` with the established schemas, status labels, blank unmatched fields, and summary keys.
