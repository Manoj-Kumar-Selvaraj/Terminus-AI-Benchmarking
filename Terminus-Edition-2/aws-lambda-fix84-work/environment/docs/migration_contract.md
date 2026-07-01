# Queue migration and cutover contract

The live target is `payments-ledger-ingestor:live`. The active queue and legacy queue are declared in `/app/config/queues.json`; controller code must resolve those references rather than embed their current ARN values. The old queue may remain for audit evidence but must not feed active processing or retain an SQS allow grant.

The mapping keeps UUID `esm-payments-ledger-live-20260613`, batch size `3`, batching window `2`, maximum concurrency `4`, one `ReportBatchItemFailures` response type, `bisect_batch_on_function_error=false`, empty `source_access_configurations`, and the exact filter representation:

```json
{"event_type": ["ledger_credit"]}
```

The migrated queue grant is one allow statement containing only `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, and `sqs:GetQueueAttributes`, scoped only to the active queue ARN. CloudWatch Logs permissions remain separate. Wildcard SQS grants, old-queue allows, `NotAction`, `NotResource`, and mixed old/new resource lists are not compatible.

Cutover validation is externally ordered:

1. Reject any source other than `active_source_queue_arn`.
2. Resolve a missing version to version 1, then reject unsupported versions.
3. For version 2, reject a non-matching epoch.
4. For an existing business identity, compare account, amount, currency, and operation before new-event operation admission.
5. For a new identity, admit only `ledger_credit`.

The exact classifications are `STALE_SOURCE_QUEUE`, `UNSUPPORTED_EVENT_VERSION`, `STALE_CUTOVER_EPOCH`, `UNSUPPORTED_OPERATION`, and `IDEMPOTENCY_CONFLICT` as declared by `/app/config/cutover_contract.json`.
