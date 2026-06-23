Extend `/app/scripts/reconcile.sh` for dated credit batches. `samples.csv` may include `result_date` and `credits.csv` may include `credit_date`. If both date columns are absent because the input uses the older milestone 1/2 CSV shape, keep the milestone 2 matching rules without applying calendar gates. If either date column is present, use dated matching for that run.

Date eligibility requires **all** of the following:

1. Both `credit_date` and the sample `result_date` are listed as `open` in `/app/config/cutoff_calendar.txt`.
2. `credit_date` is not later than `result_date` (same-day pairs are allowed).
3. The open-day count is at most two: count OPEN calendar rows strictly after `credit_date` through and including `result_date`. Same-day matches (zero open rows strictly between the dates) and exactly two open days are eligible; three or more open days are not.

Missing, malformed, closed, or unlisted dates on either side are not eligible when dated matching is active.

Worked example: with `credit_date=2026-04-10`, `result_date=2026-04-12`, and calendar rows `2026-04-11 open` and `2026-04-12 open` (and no other open rows strictly after 04-10 through 04-12), the open-day count is exactly two, so the date-span gate passes. A same-day pair `credit_date=2026-04-10` and `result_date=2026-04-10` has zero open rows strictly between the dates and is also eligible when both dates are open.

If multiple unused sample rows match one credit, choose the row with the latest `result_date`. Consumption is by row position, not `sample_id`, so duplicate ids in separate rows remain separate. Keep aliases from milestone 2 and keep the existing report and summary schemas.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
