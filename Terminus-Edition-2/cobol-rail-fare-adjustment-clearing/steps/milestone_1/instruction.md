The COBOL rail fare adjustment reconciler in `/app/src/fare_adjust_reconcile.cbl` is producing unreliable clearing reports. Fix it so it reconciles `/app/data/rides.dat` with `/app/data/adjustments.dat` and writes the required outputs under `/app/out`.

The source records and action records are fixed-width files documented in `/app/docs/record_layouts.md`. A row matches only when the full 12-character record id, 8-character account, 10-digit amount, 4-character branch, source status `C`, eligible action reason, and allowed canonical fare_class all agree. Allowed canonical fare_class values are `STD`, `EXP`, `SNR`. Eligible action reasons are `F01`, `F07`, `F11`. The action date must be on or after the matched source date. Each source row can be consumed once.

Write `/app/out/adjustment_report.csv` with columns `record_id,account,fare_class,amount_cents,reason,status`, preserving action input order and the zero-padded amount text. Trim fixed-width padding from string fields such as `record_id` and `account` before writing CSV output. Matched rows must report the canonical source `fare_class`; unmatched rows must leave the `fare_class` column truly empty, not spaces and not the action fare_class. Write `/app/out/adjustment_summary.txt` as `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with all amounts counted as positive integer cents.

The report `reason` column always echoes the trimmed three-character reason from the action record, even when that reason is ineligible and the row is `UNMATCHED`. Do not blank, normalize, or replace the action reason. Only `fare_class` is blanked on unmatched rows.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
