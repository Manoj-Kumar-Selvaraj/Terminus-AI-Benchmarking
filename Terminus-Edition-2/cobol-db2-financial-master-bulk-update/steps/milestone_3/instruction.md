# Milestone 3 — Handle DB2 lock contention without losing work

Restart is now safe, but the online-posting overlap from the incident still loses work. When a row is locked, the simulator returns DB2-style SQLCODE `-911`. The current workflow treats the locked detail like a business reject or advances beyond it, so the affected update never gets replayed.

Use `/app/data/locks/online_posting_lock.json` and `/app/data/batches/lock_044.fb` as evidence. Repair `/app/internal/finbulk/profile.go` and `/app/internal/finbulk/runner.go` and preserve all earlier behavior.

For this milestone, implement retry-safe lock handling:

- SQLCODE `-911` must be treated as retryable lock contention, not as a business reject;
- the job must stop at the locked sequence, write `pending_locks_<batch>.json`, set `summary_<batch>.json` status exactly `RETRYABLE_LOCK`, include integer field `pending_locks` with the number of pending lock rows for this run, and return process status `75`;
- checkpoint state must not advance past the locked detail;
- later records in the same run must not be processed after the locked detail;
- `rejects_<batch>.dat` must not contain SQLCODE `-911`; after the lock is cleared and the same batch is rerun, the locked detail and later details must apply exactly once.

Do not use sleeps, nondeterminism, wildcard lock clearing, or fixture-specific account names. The verifier injects its own lock state.
