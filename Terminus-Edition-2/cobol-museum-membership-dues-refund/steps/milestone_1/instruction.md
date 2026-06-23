The COBOL museum membership dues refund reconciler in `/app/src/membership_refund_reconcile.cbl` is producing unreliable clearing reports. Fix it so it reconciles `/app/data/dues.dat` with `/app/data/refunds.dat` and writes the required outputs under `/app/out`.

The source records and action records are fixed-width files documented in `/app/docs/record_layouts.md`. A row matches only when the full 12-character record id, 8-character account, 10-digit amount, 4-character branch, source status `M`, eligible action reason, and allowed canonical plan_code all agree. Allowed canonical plan_code values are `ANN`, `FAM`, `STU`. Eligible action reasons are `U01`, `U07`, `U15`. The action date must be on or after the matched source date. Each source row can be consumed once.

Write `/app/out/dues_refund_report.csv` with columns `record_id,account,plan_code,amount_cents,reason,status`, preserving action input order and the zero-padded amount text. Write `/app/out/dues_refund_summary.txt` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with all amounts counted as positive integer cents.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
