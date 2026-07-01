# Milestone 2 - Recover retries without replaying completed work

Normal batches now finish, but transient timeouts replay work that Jenkins previously resumed from durable progress. The incident created duplicate ledger and partner effects. Use `/app/evidence/lambda_retry_trace.log`, `/app/evidence/duplicate_effect_report.json`, `/app/docs/retry-idempotency-contract.md`, and `/app/docs/pipeline-contract.md`.

Repair checkpointed retry in the Go controller. Retry only the uncertain operation within the configured attempt limit; keep execution, deployment, and operation identities stable; and bracket every external effect in `/app/state/operations.journal.jsonl` with matching `STARTED` and `COMMITTED` records. A restart resumes the first unfinished stage, while an identical completed request is a no-op. Exhaustion persists `RETRY_PENDING` with the first unfinished `next_stage`; `run` and `resume` print that checkpoint then exit nonzero. Only terminal `SUCCEEDED` and `PARTIAL` results exit zero. Reject execution-ID reuse with changed batch, owner, or artifact before effects and include `conflicting` in the diagnostic.

Use the trusted deterministic clock. Do not sleep, retry without a bound, regenerate identities or effect keys, disable injected failures, or suppress errors.
