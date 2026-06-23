The COBOL warehouse storage credit reconciler in `/app/src/storage_credit_reconcile.cbl` is producing unreliable clearing reports. Fix it so it reconciles `/app/data/charges.dat` with `/app/data/credits.dat` and writes the required outputs under `/app/out`.

The source records and action records are fixed-width files documented in `/app/docs/record_layouts.md`. A row matches only when the full 12-character record id, 8-character account, 10-digit amount, 4-character branch, source status `B`, eligible action reason, and allowed canonical charge_type all agree. Allowed canonical charge_type values are `BIN`, `FLT`, `CLD`. Eligible action reasons are `C04`, `C08`, `C19`. The action date must be on or after the matched source date. Each source row can be consumed once.

Write `/app/out/credit_report.csv` with columns `record_id,account,charge_type,amount_cents,reason,status`, preserving action input order and the zero-padded amount text. Write `/app/out/credit_summary.txt` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with all amounts counted as positive integer cents.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
