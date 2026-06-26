# Milestone 2 — Recover retries without replaying completed work

The complete Lambda fleet is now visible and normal batches finish. During a transient timeout, however, the migration repeats work that Jenkins previously resumed from its last durable stage. Operations observed duplicate ledger effects and partner notifications for one execution.

Review:

- `/app/evidence/lambda_retry_trace.log`
- `/app/evidence/duplicate_effect_report.json`
- `/app/docs/retry-idempotency-contract.md`
- `/app/docs/pipeline-contract.md`

Recover durable stage progress and bounded retry behavior. A transient failure or lost response must retry only the uncertain operation, preserve the execution and deployment identity, and use a stable operation identity for every external effect. Externally visible effects must be journaled in `/app/state/operations.journal.jsonl` with matching `STARTED` and `COMMITTED` records that share one `operation_id`. A completed execution rerun must be harmless. A restart must reconstruct the request and checkpoint instead of beginning at `intake`. When the bounded attempt budget is exhausted, persist the checkpoint with status `RETRY_PENDING` and keep `next_stage` at the first unfinished stage so a later resume can continue safely.

The trusted runtime uses a deterministic clock. Do not use wall-clock sleeps, unbounded retry loops, regenerated execution IDs, or new idempotency keys on each attempt. Do not disable failure injection or suppress reported failures.
