# Escrow Clearing Runbook

Run `/app/scripts/run_batch.sh` to execute the batch. The reconciler must read all runtime inputs from `/app/data` and `/app/config` and write only under `/app/out`.

The batch processes row-level eligibility first, then closing packages, then trust funding and control totals. In the restart milestone, setting `ABEND_AFTER_GROUPS=N` simulates a deterministic failure after N new group commits. The process must exit non-zero immediately after writing the partial ledger and `status=ABENDED` checkpoint. Rerunning without that variable must resume from the committed ledger and must not duplicate any prior group.

Commit rows use `commit_id=COMMIT-<closing_id>` and `committed_at=20260613000000` in verifier scenarios.
