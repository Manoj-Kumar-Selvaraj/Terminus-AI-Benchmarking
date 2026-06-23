Extend `/app/lib/reconcile.rb` for dated refund batches. `bookings.csv` may include `show_date` and `refunds.csv` may include `refund_date`.

When **neither** input file has a `show_date` or `refund_date` column, skip date gating entirely and keep milestone 1-2 matching behavior, including exact `seat_zone` equality and aliases. Apply date rules when either file includes one of those date columns.

When date columns are in use, a refund can match only when all prior criteria still pass, both `refund_date` and `show_date` are listed as `open` in `/app/config/cutoff_calendar.txt`, and `refund_date` is before `show_date`. Count open calendar dates strictly after `refund_date` through and including `show_date`; at least two open dates are required for a refund to be eligible. Missing, closed, or unlisted dates are not open.

If multiple unused booking rows match one refund, choose the eligible row with the latest `show_date`; if `show_date` values tie, choose the earliest booking input row. Consumption is by row position, not `booking_id`, so duplicate ids in separate rows remain separate. Keep aliases from milestone 2 and keep the existing report and summary schemas with positive integer cents.
