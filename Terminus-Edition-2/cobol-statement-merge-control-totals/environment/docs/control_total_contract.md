# Control total contract

Downstream general-ledger posting consumes `/app/out/control_totals.dat`.

Requirements:

- One committed row per distinct occurrence of an `(account_id, stmt_date)` control group boundary encountered during sequential processing. If the same pair appears, closes, and reopens later in the stream, each opening produces a separate committed row; there is no cross-group deduplication.
- Example: stream groups for `(ACCT1001, 20260401)`, then `(ACCT1001, 20260402)`, then `(ACCT1001, 20260401)` again produce **three** committed rows, not two.
- `debit_cents` and `credit_cents` are independent sums of `DR` and `CR` statement amounts.
- `stmt_count` counts every statement row assigned to the group.
- `status` is always `C` for rows in the final file after a successful run.
- Summary keys in `/app/out/merge_summary.txt` must reconcile with the committed rows.

Restart runs must produce the same final totals as an uninterrupted run.
