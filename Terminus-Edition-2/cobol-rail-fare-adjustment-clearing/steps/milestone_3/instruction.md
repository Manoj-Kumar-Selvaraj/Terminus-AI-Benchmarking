Finish the rail fare adjustment reconciler in `/app/src/fare_adjust_reconcile.cbl` by applying calendar gates from `/app/config/service_calendar.txt`. Preserve all established matching, alias, report, summary, action-order, and source-consumption behavior, including raw action reasons and blank `fare_class` values for every unmatched report row.

Source dates are eligible only when the same date appears in the calendar file with the literal state `OPEN` compared case-insensitively; closed, missing, unlisted, or malformed dates are ineligible. All earlier matching gates still apply, including aliases, consumption, status `C`, reasons, and allowed categories.

When more than one unused source row matches an action, choose the eligible row with the latest source date. If source dates tie, choose the earliest source input row. Consumption is tracked by source row position, not by record id alone.

Also write `/app/out/source_consumption.csv` so operations can audit the physical rows selected by the batch. Its exact header is `action_record_id,source_row,source_date`. Write one row for each matched action, in action order. `action_record_id` is the trimmed action id, `source_row` is the selected source record's one-based input position formatted as four digits, and `source_date` is that source record's eight-character date. Do not write trace rows for unmatched actions.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/adjustment_report.csv` and `/app/out/adjustment_summary.txt` with the established schemas, status labels, trimmed CSV identifiers, blank unmatched fields, raw action reasons, and summary keys.
