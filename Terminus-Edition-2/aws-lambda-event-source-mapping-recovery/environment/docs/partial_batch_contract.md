# Partial-batch response contract

A successful handler invocation returns exactly one top-level `batchItemFailures` array. Each failed record is represented once by an object whose `itemIdentifier` is the input SQS `messageId`. Failures are reported in input order even when asynchronous processing completes in another order. Empty input returns exactly `{"batchItemFailures": []}`.

Failure objects are closed schemas. Parsing, schema-invalid, and fixture-poison failures are exactly:

```json
{"itemIdentifier": "<messageId>"}
```

Cutover-classified failures are exactly:

```json
{"itemIdentifier": "<messageId>", "failureClassification": "<configured value>"}
```

Do not add diagnostic fields such as `reason`, `failureReason`, `failureType`, or `classification` to the handler response. Diagnostics belong in durable sidecars or DLQ evidence, not in the Lambda partial-batch response.

Classified poison, malformed, schema, and cutover failures do not block successful peers. Records absent from the failure list are treated as successful and deleted by the simulator. The handler must not mutate the inbound `Records` objects.

An unexpected infrastructure error fails the invocation instead of being converted into all-record retries. Infrastructure errors are not partial-batch failures: the whole batch is aborted, the handler emits no successful response, and the ledger must remain exactly as it was before the invocation. A valid peer record in the same batch must not commit before the infrastructure error is rethrown; use a validation/classification phase before durable writes or an equivalent rollback guarantee.

Cutover failures also include `failureClassification` with the exact configured value from `/app/config/cutover_contract.json`. Earlier parsing, schema, malformed JSON, and fixture poison failures identify only the failed item.
