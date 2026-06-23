Extend `/app/lib/reconcile.rb` for dated refund batches while keeping all previous behavior. If both
CSV files use the earlier schemas without date columns, keep the prior matching behavior. When
either input includes dates, appointments require a valid ISO `service_date` column and refunds
require a valid ISO `refund_date` column. Valid dates use exact `YYYY-MM-DD` form. A refund is
eligible only when all prior gates pass, the `refund_date` is listed as `open` in
`/app/config/cutoff_calendar.txt` case-insensitively, and `refund_date <= service_date`. Calendar
lines may contain comments or blanks; closed, missing, unlisted, malformed, or invalid dates are not
eligible.

If multiple unused appointment rows match one dated refund after all gates, select the
row with the latest `service_date`; if service dates tie, choose the earliest appointment input row.
Consumption remains by physical row position, not by appointment id. Runtime aliases from the
previous step still apply.

Regenerate `/app/out/appointment_selection.csv` with this exact header:

```text
refund_row,appointment_row,service_date
```

Write one trace row for each matched refund in refund input order. `refund_row` and
`appointment_row` are zero-based physical data-row positions; CSV headers are not counted.
`service_date` is copied from the selected appointment row. When date columns are absent from
both feeds, write only the header row with no data lines. Unmatched refunds do not appear in the
trace.

Keep the same report and summary schemas, status labels, blank unmatched
service field, amount preservation, and invalid-row accounting.
