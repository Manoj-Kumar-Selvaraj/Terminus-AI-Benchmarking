Finish the hospital claim denial reconciler in `/app/src/claim_denial_reconcile.cbl` by applying calendar gates from `/app/config/adjudication_calendar.txt` while preserving existing matching, alias, consumption, report, and summary behavior. Report `record_id` and `account` as trimmed logical CSV values without the leading type byte or fixed-width padding.

Source dates are eligible only when the same date appears in the calendar file with the literal state `OPEN` compared case-insensitively; closed, missing, unlisted, or malformed dates are ineligible when a date comparison is required. When only one side has a blank source date or action date, treat the pair as ineligible for clearing. When both the source date and action date are blank on a candidate pair, treat the row like the undated path from prior work and skip calendar gates. All prior matching gates still apply, including aliases, consumption, status `A`, eligible reasons, and allowed canonical source services `ER`, `LAB`, and `IMG`; source-side alias spellings such as `E1`, `LB`, or `XR` are not canonical source services and must remain ineligible.

When more than one unused source row matches an action, choose the eligible row with the latest source date. If source dates tie, choose the earliest source input row. Consumption is tracked by source row position, not by record id alone.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Continue to write `/app/out/denial_report.csv` and `/app/out/denial_summary.txt` with the same schemas, status labels, literal `,,` blank unmatched service fields, action reason values for both matched and unmatched report rows, and summary keys.

Also write `/app/out/source_consumption.csv` for matched rows only. Its header must be `action_record_id,source_row,source_date`; `source_row` is the one-based physical source input row formatted as four digits, and rows appear in denial action order.
