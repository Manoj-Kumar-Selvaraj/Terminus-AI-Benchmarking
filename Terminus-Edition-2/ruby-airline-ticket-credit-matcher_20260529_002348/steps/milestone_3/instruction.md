Extend `/app/lib/reconcile.rb` for dated credit batches. `tickets.csv` may include `flight_date` and `credits.csv` may include `credit_date`.

When **neither** input file has a `flight_date` or `credit_date` column, skip date gating entirely and keep milestone 1–2 matching behavior (including exact `fare_class` equality and aliases). Apply date rules only when at least one file includes the corresponding date column. This is different from a row where the column exists but the cell is blank: absent columns mean legacy undated matching; blank values in a present column are ineligible in dated mode.

When date columns are in use, a credit can match only when all prior criteria still pass, `credit_date` is listed as `open` in `/app/config/cutoff_calendar.txt`, and `credit_date` is not later than the ticket `flight_date` (equal calendar days are eligible). Missing, closed, or unlisted `credit_date` values are not eligible. A ticket with missing `flight_date` is not eligible in this dated mode.

If multiple unused ticket rows match one credit, choose the row with the latest `flight_date`; if dates tie, choose the earliest ticket input row. Consumption is by row position, not `ticket_id`, so duplicate ids in separate rows remain separate. Keep aliases from milestone 2 and keep the existing report and summary schemas with positive integer cents.
