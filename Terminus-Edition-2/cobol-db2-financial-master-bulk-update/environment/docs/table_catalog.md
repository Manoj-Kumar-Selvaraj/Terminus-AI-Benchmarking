# Simulator table catalog

The offline DB2-style state file contains the following logical tables:

- `master`: financial master account rows updated by BAL, RAT, HLD, and LIM details.
- `risk`: risk profile rows that must remain consistent with master credit limits.
- `ledger`: monetary side effects from committed BAL details.
- `audit`: committed detail markers for operator traceability.
- `rejects`: permanent business rejects such as missing master rows and failed constraints.
- `pending_locks`: retryable lock-contention records from SQLCODE -911.
- `checkpoint`: highest committed sequence per batch.
- `applied_events`: idempotency markers keyed by batch and sequence.
