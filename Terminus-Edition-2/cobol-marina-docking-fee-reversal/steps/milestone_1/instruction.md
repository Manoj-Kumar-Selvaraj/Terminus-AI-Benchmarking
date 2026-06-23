The COBOL marina docking fee reversal reconciler in `/app/src/docking_reversal_reconcile.cbl` is producing unreliable clearing reports. Fix it so it reconciles `/app/data/dock_fees.dat` with `/app/data/reversals.dat` and writes the required outputs under `/app/out`.

The source records and action records are fixed-width files documented in `/app/docs/record_layouts.md`. A row matches only when the full 12-character record id, 8-character account, 10-digit amount, 4-character branch, source status `D`, eligible action reason, and allowed canonical berth_type all agree. Allowed canonical berth_type values are `SLP`, `DRY`, `TRN`. Eligible action reasons are `H02`, `H06`, `H13`. The action date must be on or after the matched source date. Each source row can be consumed once.

Write `/app/out/docking_reversal_report.csv` with columns `record_id,account,berth_type,amount_cents,reason,status`, preserving action input order and the zero-padded amount text. Write `/app/out/docking_reversal_summary.txt` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with all amounts counted as positive integer cents.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
