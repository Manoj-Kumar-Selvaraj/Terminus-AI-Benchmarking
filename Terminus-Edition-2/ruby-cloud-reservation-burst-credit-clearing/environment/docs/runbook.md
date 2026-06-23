# Runbook

If the batch is interrupted with `ABEND_AFTER_GROUPS`, the process must exit with status code `17` after writing the partial ledger and checkpoint. Rerun the same command without changing inputs. The rerun must read `/app/out/credit_commit_ledger.csv` and `/app/out/restart_checkpoint.txt`, avoid committing already committed groups again, and continue pending groups.
