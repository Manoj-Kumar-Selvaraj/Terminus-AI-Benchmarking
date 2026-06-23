Extend the visit credit reconciler in `/app/cmd/reconcile/main.go` to handle dated credit batches. It must still read `/app/data/visits.csv` and `/app/data/credits.csv`, then write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schema and status values from the earlier milestones.

`visits.csv` may include a `due_date` column and `credits.csv` may include a `credit_date` column. See `/app/docs/record_layouts.md` and `/app/docs/date_gating.md`.

When **neither** input file has a `due_date` or `credit_date` column, skip date gating entirely and keep milestone 1-2 matching behavior (including aliases, full visit id equality, row consumption, and positive matched cents). Apply date rules only when at least one file includes the corresponding date column. This differs from a row where the column exists but the cell is blank: absent columns mean legacy undated matching; blank values in a present column are ineligible in dated mode.

When date columns are in use, a credit can match only when all prior criteria still pass, the `credit_date` is listed as `open` in `/app/config/cutoff_calendar.txt`, and the `credit_date` is not later than the visit `due_date` (equal calendar days are eligible). Missing, closed, or unlisted `credit_date` values are not eligible. A visit with a missing `due_date` is not eligible in this dated mode.

If more than one unused visit row matches one credit, choose the row with the latest `due_date`; if dates tie, choose the earliest visit input row. Consumption is by visit row position, not by visit id, so duplicate visit ids remain separate rows. Each visit row can still be consumed at most once.

Legacy aliases from milestone 2 still apply (`CC` means `CARD`, `WIR` means `WIRE`), and matched report rows must emit the canonical channel. Unmatched rows must leave `channel` blank. Summary amounts remain positive integer cents.
