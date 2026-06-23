Make `/app/app/reconcile.rb` restart-safe after a batch ABEND while preserving all row, package, funding, and control-total rules. See `/app/docs/runbook.md` and `/app/docs/support_matrix.md`.

With `ABEND_AFTER_GROUPS=N`, commit exactly the first N newly cleared groups in processing order, write the checkpoint, then exit non-zero. Before exiting, regenerate every prior output, including `/app/out/disbursement_report.csv`, `/app/out/disbursement_summary.txt`, `/app/out/closing_group_report.csv`, and `/app/out/trust_balance_after.csv`; balances must equal the clean-run funding result. Normally, commit every cleared group once at package boundaries.

Write `/app/out/escrow_commit_ledger.csv` with columns `commit_id,closing_id,trust_id,amount,committed_at`. Use `commit_id`=`COMMIT-<closing_id>` (for example `COMMIT-CLOSE-1`) and `committed_at`=`20260613000000` (fixed 14-digit UTC batch timestamp, not the current clock). Each clearing group may appear at most once across reruns.

Write `/app/out/restart_checkpoint.txt` with exactly three `key=value` lines using these keys: `last_committed_closing_id`, `committed_count`, and `status` set to `ABENDED` or `COMPLETE`. Example after committing one group then ABEND:
```
last_committed_closing_id=CLOSE-1
committed_count=1
status=ABENDED
```
On restart, read the ledger, skip committed groups, continue pending clearable groups, and leave held groups uncommitted. Successful reruns must not change balances or duplicate commits.
