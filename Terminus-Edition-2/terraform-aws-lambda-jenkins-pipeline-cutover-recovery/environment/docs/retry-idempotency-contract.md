# Retry, Checkpoint, and Idempotency Contract

Transient Lambda or control-plane failures may be retried at most three times per stage operation. The implementation must not use `time.Sleep` to model retry timing. The trusted runtime exposes a deterministic clock.

## Operation journal

Externally visible effects are recorded in `/app/state/operations.journal.jsonl`. Each effect uses one stable `operation_id` across retries and restarts. A successful effect produces exactly two durable records for that operation: `STARTED` then `COMMITTED`, both sharing the same `operation_id`, `execution_id`, `stage`, `generation`, and `epoch`.

## Checkpoint output

`pipelinectl run` and `pipelinectl resume` print the durable execution checkpoint as JSON. Required fields include:

```text
execution_id
batch_id
owner
protocol_version
artifact_digest
generation
epoch
next_stage
status
metadata
items
completed_effects
attempts
updated_at
```

`protocol_version` and `owner` are preserved from the accepted request envelope. `epoch` records the trusted runtime epoch pinned for the execution. `status` becomes `RETRY_PENDING` when the bounded attempt budget is exhausted.

A durable checkpoint is written after each completed stage. Resume starts at the first unfinished stage and does not replay completed work.
When all three attempts for a stage operation are exhausted, the durable checkpoint status is exactly `RETRY_PENDING`. Its `next_stage` remains the zero-based index of the first unfinished pipeline stage. A later `resume` or reconciliation pass may continue from that checkpoint after the transient fault is cleared.

The following operations are externally visible and require stable operation identities across retries, lost responses, and process restarts:

- one ledger write per batch item,
- one report publication per batch,
- one partner notification per batch,
- one archive operation per batch.

A response may be lost after the trusted runtime commits an effect. Retrying the same operation must recover the committed result rather than creating another effect.
