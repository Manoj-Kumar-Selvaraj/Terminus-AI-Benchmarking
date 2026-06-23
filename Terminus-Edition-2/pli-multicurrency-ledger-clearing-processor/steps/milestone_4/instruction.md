The treasury desk now reports that the batch can clear individual rows while still violating account-level clearing controls after an interrupted run. Fix only the PL/I-style control files under `/app/src`. Do not modify `/app/scripts/run_batch.sh` or `/app/scripts/pli_ledger.awk`.

Preserve strict matching, alias normalization, FX-window checks, row consumption, report, and summary behavior while adding group-level control totals and restart-safe commit boundaries. Matched rows roll up by `account_id`, `desk_id`, and canonical `currency_code` after alias normalization. A group may commit only when `/app/config/control_totals.psv` contains a matching group and the actual cleared row count and native amount reconcile within `tolerance_cents`; otherwise every row in that group becomes `HELD` with blank `currency_code` in the row report.

Keep `/app/out/ledger_report.csv` and `/app/out/ledger_summary.txt` on the same pipe-delimited schemas already used by the row-clearing report. Status remains exactly `CLEARED` or `HELD` on row report rows.

Write `/app/out/clearing_groups.psv` as pipe-separated text with this exact header:

`account_id|desk_id|currency_code|actual_count|actual_amount_cents|expected_count|expected_amount_cents|tolerance_cents|status`

Emit one row per clearing group. Use group status exactly `COMMITTED` when the group passes control totals, or `HELD_CONTROL` when the group is missing from control totals or fails count or amount reconciliation within tolerance.

Write `/app/out/clearing_commits.psv` as pipe-separated text with this exact header:

`account_id|desk_id|currency_code|cleared_count|cleared_amount_cents`

Append one row per committed group. A restarted batch must not duplicate rows for groups already committed before an ABEND.

Write `/app/out/restart_checkpoint.txt` containing exactly one line:

`last_committed_group=<account_id>|<desk_id>|<currency_code>`

Use the last committed clearing group after the run finishes.

The existing batch harness can simulate an interrupted run through its ABEND hook; preserve that behavior. When an ABEND occurs after a committed group, a rerun must not duplicate already committed groups and must still process pending groups. Preserve posting order, dynamic rule constants, alias normalization, FX-window checks, one-use ledger consumption, and integer summary totals.
