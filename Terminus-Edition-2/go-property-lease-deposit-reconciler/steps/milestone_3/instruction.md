Support dated deposit batches. `/app/data/leases.csv` may include a `due_date` column and `/app/data/deposits.csv` may include a `deposit_date` column. Dated mode activates when either file includes its date column. When neither column is present, skip date gating and preserve the existing matching and alias behavior.

A deposit can match only when all existing criteria pass, the deposit date is listed as `open` in `/app/config/cutoff_calendar.txt`, and the deposit date is not later than the lease due date. Dates used for `due_date` and `deposit_date` must be valid `YYYY-MM-DD` strings. Blank, missing, malformed, or otherwise non-comparable date values are ineligible and must not crash the CLI. A missing or closed deposit date is not eligible. A lease with a missing due date is also ineligible because the date comparison cannot be satisfied.

If more than one unused lease row matches the same deposit, choose the eligible lease row with the latest due date. If due dates tie, choose the earliest lease row. Consumption is tracked per input row, not by `lease_id`; duplicate lease IDs are independent rows that can each be consumed once.

Legacy aliases still apply (`CC` means `CARD`, `WIR` means `WIRE`), and matched report rows must emit the canonical channel. Unmatched rows must leave `channel` blank. Summary amounts remain positive integer cents.
