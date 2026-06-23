Fix the Ruby reconciler in `/app/lib/reconcile.rb`. It must read `/app/data/appointments.csv` and
`/app/data/refunds.csv`, then write `/app/out/refund_report.csv` and `/app/out/refund_summary.json`.
Parse both CSV files by header name, not column position; required columns are `appointment_id`,
`client_id`, `amount_cents`, `status`, and `service_area` for appointments, and `appointment_id`,
`client_id`, `amount_cents`, and `service_area` for refunds. Extra columns may appear and must be
ignored.

A refund matches only one unused appointment row when all of these gates pass after
trimming surrounding spaces: full `appointment_id` equality, full `client_id` equality, positive
base-10 integer `amount_cents` equality, appointment status `COMPLETED` case-insensitively, and the
same canonical service area. The canonical service areas in this step are `MASSAGE`, `FACIAL`, and
`SAUNA`; service comparison is case-insensitive, and matched report rows must emit the canonical
uppercase value. Prefix, substring, fuzzy, partial-id, unsupported-service, malformed-amount, zero-
amount, negative-amount, decimal-amount, and non-`COMPLETED` rows are not eligible. Consume
appointments by physical row position, so one appointment row cannot satisfy two refund rows.

The
report schema is exactly `appointment_id,client_id,service_area,amount_cents,status` in refund input
order. Use only `MATCHED` and `UNMATCHED`; leave `service_area` blank for unmatched rows. The report
`amount_cents` value must preserve the trimmed refund input string verbatim, including leading
zeros. The JSON summary must contain integer `matched_count`, `matched_amount_cents`,
`unmatched_count`, and `unmatched_amount_cents`. Every unmatched refund row, including malformed
amount rows, increments `unmatched_count`; invalid amounts do not contribute to either amount total.
Regenerate both output files on every run.
