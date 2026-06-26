# Milestone 3 — Isolate poison work and concurrent batches

Checkpointed retry has stopped the duplicate-effect incident. Queue depth remains high because one invalid settlement item still causes all valid siblings to be retried, and overlapping executions for the same batch can both reach externally visible stages.

Review:

- `/app/evidence/partial_batch_trace.log`
- `/app/docs/fanout-contract.md`
- `/app/docs/retry-idempotency-contract.md`

Make the item portion of the workflow failure-isolated. Permanently invalid items must receive exactly the documented three validation attempts before being recorded in the trusted DLQ, while valid siblings continue through ledger publication. The batch result must distinguish partial completion from full success.

Enforce one execution owner per batch without globally serializing unrelated batches. A second execution must not publish the same batch after the first owner releases its transient lock. Locks must still be released on successful and partial completion.

Do not delete invalid records, mark every item successful, disable concurrency, or route all batches through a single global lock.
