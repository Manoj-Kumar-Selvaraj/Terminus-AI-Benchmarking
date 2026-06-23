# Coworking CSV record layout

`bookings.csv` and `credits.csv` are simple comma-delimited files without quoted commas. Columns may be reordered and extra columns may appear; address fields by header name.

Booking rows use `booking_id`, `member_id`, `amount_cents`, `status`, and `plan`. Dated batches add `booking_date` as a strict `YYYY-MM-DD` value.

Credit rows use `booking_id`, `member_id`, `amount_cents`, and `plan`. Dated batches add `credit_date` as a strict `YYYY-MM-DD` value.

The report file is `/app/out/credit_report.csv` and uses `booking_id,member_id,plan,amount_cents,status` with one row per credit input row. The summary file is `/app/out/credit_summary.json` and stores integer counts and positive cent totals derived from the report.
