# Restart runbook

FNBULKUP is restartable at the committed detail-record boundary. The same batch can be rerun after a simulated or real ABEND.

Required restart behavior:

1. A committed detail record must have exactly one audit marker in `audit` and exactly one event marker in `applied_events`.
2. `BAL` records must have exactly one ledger row per committed event.
3. Rerunning an already completed batch must skip committed records and leave balances, audit rows, ledger rows, and checkpoints stable.
4. SQLCODE `-911` is retryable. Stop at the locked record, write `pending_locks_<batch>.json`, and leave later records unprocessed until a rerun after the lock is cleared.
5. Business rejects (`+100`, `-530`) should be reported but must not create applied-event markers.
6. Mutating runs must hold an exclusive `flock` on `<dirname(db)>/.lock_<batch_id>` for their entire critical section. Concurrent same-batch invocations exit with status `73` and summary status `BATCH_BUSY` without mutating any simulator table. The lock file is reusable after a crash because OS-level flock is released on process death; never gate fencing on a recorded PID.
7. `--abend-after-lim-master` aborts mid-LIM after the master commit but before the risk commit. The runner must roll back the in-process master half so durable state shows neither half applied; a later rerun must apply that LIM exactly once across both tables.
8. Daily close mode (`--close DATE`) is read-only. It replays `chain_index[DATE]` in order, recomputes each `chain_sha256` link, and writes `close_<DATE>.json` and `glfeed_<DATE>.dat`. Close never acquires a per-batch lock and never mutates simulator state. Chain breakage produces summary status `CLOSE_BROKEN` and an empty GL feed.
9. A control manifest may declare an optional `prior_batch_id`. The named batch must already be `SETTLED` on the same business date and must be the current chain tip; otherwise the run fails closed with `UNMET_DEPENDENCY` and no state changes.
