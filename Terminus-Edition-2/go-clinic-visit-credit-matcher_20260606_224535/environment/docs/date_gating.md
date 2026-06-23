# Credit date gating

Date controls apply when either `visits.csv` includes a `due_date` column or `credits.csv` includes a `credit_date` column. When neither column is present, skip calendar checks and use milestone 1–2 matching rules.

In dated mode, both the visit `due_date` and credit `credit_date` must be nonblank, the credit date must be listed as `open` in `/app/config/cutoff_calendar.txt`, and the credit date must not be later than the visit due date. Blank date cells on dated files remain ineligible.

When multiple eligible visits remain, choose the latest `due_date`; ties break to the earliest visit input row.
