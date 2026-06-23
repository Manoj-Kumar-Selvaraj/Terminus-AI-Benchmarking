# Restart runbook

FNBULKUP is restartable at the committed detail-record boundary. The same batch can be rerun after a simulated or real ABEND.

Required restart behavior:

1. A committed detail record must have exactly one audit marker in `audit` and exactly one event marker in `applied_events`.
2. `BAL` records must have exactly one ledger row per committed event.
3. Rerunning an already completed batch must skip committed records and leave balances, audit rows, ledger rows, and checkpoints stable.
4. SQLCODE `-911` is retryable. Stop at the locked record, write `pending_locks_<batch>.json`, and leave later records unprocessed until a rerun after the lock is cleared.
5. Business rejects (`+100`, `-530`) should be reported but must not create applied-event markers.
