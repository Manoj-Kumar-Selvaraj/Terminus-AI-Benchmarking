# Record Layouts

The escrow batch uses CSV fixtures but it is not a row-to-row matcher. The final clearing decision is made at the closing-package level and then committed through a restart-safe ledger.

## Core inputs

- `/app/data/holds.csv`: source escrow hold rows.
- `/app/data/disbursements.csv`: disbursement instructions. Later milestones include `closing_id`.
- `/app/config/windows.csv`: realtime trust-account windows.
- `/app/config/closing_packages.csv`: closing package required kinds and expected totals. `required_kinds` uses `|` between canonical kind tokens.
- `/app/data/trust_balances.csv`: opening funding balance per trust account.
- `/app/config/control_totals.csv`: operator control totals per trust account.

## Core outputs

- `/app/out/disbursement_report.csv`: row-level match result in action order.
- `/app/out/disbursement_summary.txt`: row-level count and amount totals.
- `/app/out/closing_group_report.csv`: group-level package clearing state. `reason` uses one token: `OK`, `PACKAGE_NOT_OPEN`, `NO_MATCHED_ROWS`, `UNMATCHED_ACTION`, `MISSING_KIND:<KIND>`, `TOTAL_MISMATCH`, `INSUFFICIENT_FUNDS`, or `CONTROL_TOTAL_MISMATCH`.
- `/app/out/trust_balance_after.csv`: funding state after committed package clearing.
- `/app/out/escrow_commit_ledger.csv`: restart-safe committed group ledger. `commit_id` is `COMMIT-<closing_id>` and `committed_at` is a 14-digit UTC timestamp.
- `/app/out/restart_checkpoint.txt`: three lines `last_committed_closing_id=<id>`, `committed_count=<n>`, and `status=ABENDED` or `status=COMPLETE`.
